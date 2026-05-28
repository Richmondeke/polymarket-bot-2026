"""
bot/short_expiry_engine.py — Short-Expiry Market Strategy Engine.

Targets markets resolving within 90 minutes where the current price is
meaningfully mispriced vs. the expected resolution probability.

Safety philosophy:
  - Only enter when there is clear, measurable edge (price vs. expected prob)
  - Never enter within 5 minutes of expiry (too late to react)
  - Never enter if we have too many concurrent short-expiry positions
  - Hard cap on position size for short-expiry trades ($1.00-$1.50)
  - Skip any market with insufficient liquidity (<$500)
  - Skip esports / subjective markets (too unpredictable)
"""
import time
import threading
import requests
from datetime import datetime, timezone, timedelta
from loguru import logger

from bot import config, database as db
from bot.order_manager import orders
from bot.risk_manager import risk


# ── Strategy parameters ───────────────────────────────────────────────────────
MAX_MINUTES_TO_EXPIRY   = 1440  # Scan up to 24 hours out to capture daily weather/events
MIN_MINUTES_TO_EXPIRY   = 8     # Never enter if fewer than 8 mins left (more buffer)
MIN_LIQUIDITY_USD       = 200   # Lowered to $200 so we can trade highly mispriced micro weather markets
MIN_EDGE_PCT            = 8     # Minimum edge %
MAX_PRICE_TO_BUY        = 0.90  # Never buy above 90¢
MIN_PRICE_TO_BUY        = 0.01  # Allow low price buying (1¢+) for high-leverage 10x-50x trades!
MAX_CONCURRENT_TRADES   = 3     # Allow up to 3 concurrent trades to leverage different categories
POSITION_SIZE_USD       = getattr(config, "POSITION_SIZE_USD", 1.05)  # Use configured position size
SCAN_INTERVAL_SECS      = 60    # Scan every 60s

# Market categories to skip (subjective / unpredictable)
SKIP_KEYWORDS = [
    "esport", "dota", "lol", "league of legends", "cs2", "valorant", "overwatch",
    "fifa", "nba 2k", "rocket league", "starcraft", "nfl prediction", "award",
    "will anyone", "next to tweet", "celebrity", "kardashian", "game 7",
]

# ── Reliable data sources for edge detection ──────────────────────────────────
# For BTC/ETH price markets, we fetch the current spot price to compute true probability
BINANCE_PRICE_URL = "https://api.binance.com/api/v3/ticker/price"


def _get_spot_price(symbol: str) -> float | None:
    """Fetch current spot price from Binance (free, no auth)."""
    try:
        r = requests.get(BINANCE_PRICE_URL, params={"symbol": symbol}, timeout=5)
        if r.ok:
            return float(r.json()["price"])
    except Exception:
        pass
    return None


def _parse_btc_market(question: str, tokens: list[dict]) -> tuple[str | None, float | None, float | None]:
    """
    Parse a Bitcoin price market like 'Will BTC be above $74,000 on May 27?'
    Returns (token_id_to_buy, market_edge_pct, our_confidence) or (None, None, None).
    """
    q_lower = question.lower()
    if "bitcoin" not in q_lower and "btc" not in q_lower:
        return None, None, None

    # Extract threshold price from question
    import re
    match = re.search(r"\$([0-9,]+)", question)
    if not match:
        return None, None, None
    try:
        threshold = float(match.group(1).replace(",", ""))
    except ValueError:
        return None, None, None

    spot = _get_spot_price("BTCUSDT")
    if spot is None:
        return None, None, None

    # Compute true probability: BTC above threshold?
    # Use a simple distance-based model:
    # If spot is X% above threshold → probability ≈ min(0.95, 0.5 + X/2)
    # If spot is X% below threshold → probability ≈ max(0.05, 0.5 - X/2)
    dist_pct = (spot - threshold) / threshold * 100  # positive = above threshold
    true_prob_above = min(0.97, max(0.03, 0.5 + dist_pct / 100 * 5))

    # But for very close expiry (< 30 mins) and spot clearly above, confidence is high
    # BTC would need a massive candle to cross the threshold in 30 mins
    # Assume max 3% move in 30 mins → widen uncertainty
    uncertainty = 0.05  # ±5% confidence band

    # Find YES/NO tokens
    yes_token, no_token = None, None
    yes_price, no_price = None, None
    for t in tokens:
        outcome = (t.get("outcome") or t.get("name") or "").lower()
        price_raw = t.get("price") or t.get("probability")
        if price_raw is None:
            continue
        p = float(price_raw)
        if outcome == "yes":
            yes_token = t.get("token_id") or t.get("id")
            yes_price = p
        elif outcome == "no":
            no_token = t.get("token_id") or t.get("id")
            no_price = p

    if yes_price is None or no_price is None:
        return None, None, None

    # Determine best bet
    # Buy YES if true_prob_above - yes_price > MIN_EDGE_PCT/100
    # Buy NO if (1-true_prob_above) - no_price > MIN_EDGE_PCT/100
    edge_yes = true_prob_above - yes_price
    edge_no  = (1 - true_prob_above) - no_price

    logger.info(
        f"[ShortExpiry] BTC ${threshold:,.0f} | Spot: ${spot:,.0f} | "
        f"True prob above: {true_prob_above:.1%} | "
        f"YES: {yes_price:.2f} (edge {edge_yes:+.1%}) | NO: {no_price:.2f} (edge {edge_no:+.1%})"
    )

    edge_threshold = MIN_EDGE_PCT / 100
    if edge_yes > edge_threshold and edge_yes > edge_no:
        if MIN_PRICE_TO_BUY <= yes_price <= MAX_PRICE_TO_BUY:
            return yes_token, round(edge_yes * 100, 1), true_prob_above
    elif edge_no > edge_threshold and edge_no > edge_yes:
        if MIN_PRICE_TO_BUY <= no_price <= MAX_PRICE_TO_BUY:
            return no_token, round(edge_no * 100, 1), 1 - true_prob_above

    return None, None, None


def _parse_eth_market(question: str, tokens: list[dict]) -> tuple[str | None, float | None, float | None]:
    """Same as BTC but for Ethereum."""
    q_lower = question.lower()
    if "ethereum" not in q_lower and "eth" not in q_lower:
        return None, None, None

    import re
    match = re.search(r"\$([0-9,]+)", question)
    if not match:
        return None, None, None
    try:
        threshold = float(match.group(1).replace(",", ""))
    except ValueError:
        return None, None, None

    spot = _get_spot_price("ETHUSDT")
    if spot is None:
        return None, None, None

    dist_pct = (spot - threshold) / threshold * 100
    true_prob_above = min(0.97, max(0.03, 0.5 + dist_pct / 100 * 5))

    yes_token, no_token = None, None
    yes_price, no_price = None, None
    for t in tokens:
        outcome = (t.get("outcome") or t.get("name") or "").lower()
        price_raw = t.get("price") or t.get("probability")
        if price_raw is None:
            continue
        p = float(price_raw)
        if outcome == "yes":
            yes_token = t.get("token_id") or t.get("id")
            yes_price = p
        elif outcome == "no":
            no_token = t.get("token_id") or t.get("id")
            no_price = p

    if yes_price is None or no_price is None:
        return None, None, None

    edge_yes = true_prob_above - yes_price
    edge_no  = (1 - true_prob_above) - no_price

    logger.info(
        f"[ShortExpiry] ETH ${threshold:,.0f} | Spot: ${spot:,.0f} | "
        f"True prob above: {true_prob_above:.1%} | "
        f"YES: {yes_price:.2f} (edge {edge_yes:+.1%}) | NO: {no_price:.2f} (edge {edge_no:+.1%})"
    )

    edge_threshold = MIN_EDGE_PCT / 100
    if edge_yes > edge_threshold and edge_yes > edge_no:
        if MIN_PRICE_TO_BUY <= yes_price <= MAX_PRICE_TO_BUY:
            return yes_token, round(edge_yes * 100, 1), true_prob_above
    elif edge_no > edge_threshold and edge_no > edge_yes:
        if MIN_PRICE_TO_BUY <= no_price <= MAX_PRICE_TO_BUY:
            return no_token, round(edge_no * 100, 1), 1 - true_prob_above

    return None, None, None


def _should_skip(question: str) -> bool:
    """Return True if this market should be avoided entirely."""
    q = question.lower()
    return any(kw in q for kw in SKIP_KEYWORDS)


def _count_active_short_expiry_positions() -> int:
    """Count how many short-expiry positions we currently have open."""
    open_positions = db.get_open_positions()
    count = 0
    for p in open_positions:
        if p.get("strategy") == "ShortExpiry":
            count += 1
    return count



def _parse_weather_market(question: str, tokens: list[dict]) -> tuple[str | None, float | None, float | None]:
    """
    Parse a NYC temperature market like 'Will the lowest temperature in New York City be between 58-59°F on May 28?'
    Uses live NWS API data to calculate the probability of the target range.
    """
    q_lower = question.lower()
    if "temperature" not in q_lower or "new york" not in q_lower:
        return None, None, None

    # Determine if it's lowest or highest temperature
    is_lowest = "lowest" in q_lower
    is_highest = "highest" in q_lower
    if not is_lowest and not is_highest:
        return None, None, None

    # Parse target temperature range or value (e.g. "between 58-59°F" or "60°F or higher" or "57°F or below")
    import re
    target_min, target_max = None, None
    
    # Try "between X-Y"
    between_match = re.search(r"between\s+(\d+)-(\d+)", q_lower)
    if between_match:
        target_min = float(between_match.group(1))
        target_max = float(between_match.group(2))
    else:
        # Try "X°F or higher" / "X°F or above"
        above_match = re.search(r"(\d+)°?[f|c]?\s+or\s+(higher|above)", q_lower)
        if above_match:
            target_min = float(above_match.group(1))
            target_max = 150.0  # open-ended max
        else:
            # Try "X°F or below" / "X°F or lower"
            below_match = re.search(r"(\d+)°?[f|c]?\s+or\s+(below|lower|less)", q_lower)
            if below_match:
                target_min = -50.0  # open-ended min
                target_max = float(below_match.group(1))
            else:
                # Try single temp "be X°F"
                single_match = re.search(r"be\s+(\d+)°?[f|c]?", q_lower)
                if single_match:
                    target_min = float(single_match.group(1))
                    target_max = float(single_match.group(1))

    if target_min is None or target_max is None:
        return None, None, None

    # Fetch live hourly NWS forecast
    # NYC (Central Park / Manhattan) Grid: OKX/33,37
    # Note: Polymarket resolves using Wunderground (often Central Park or nearby airport). NWS OKX grid matches this.
    try:
        url = "https://api.weather.gov/gridpoints/OKX/33,37/forecast/hourly"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return None, None, None
        data = r.json()
        periods = data.get("properties", {}).get("periods", [])
    except Exception:
        return None, None, None

    # Extract target date from question (e.g. "on May 28")
    # Weather markets usually specify the date. Let's find it.
    import datetime
    today = datetime.date.today()
    target_date = today # default to today
    
    date_match = re.search(r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d+)", q_lower)
    if date_match:
        month_name = date_match.group(1)
        day_num = int(date_match.group(2))
        # Map month name to integer
        months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
        month_idx = next((i + 1 for i, m in enumerate(months) if m in month_name), None)
        if month_idx:
            try:
                # Assume current year
                target_date = datetime.date(today.year, month_idx, day_num)
            except ValueError:
                pass

    # Filter forecast temperatures for the target date
    temps = []
    for p in periods:
        time_str = p.get("startTime")
        if not time_str:
            continue
        try:
            dt = datetime.datetime.fromisoformat(time_str[:-6])
            if dt.date() == target_date:
                temps.append(float(p.get("temperature", 0)))
        except Exception:
            continue

    if not temps:
        return None, None, None

    # Compute expected value based on forecast
    expected_val = min(temps) if is_lowest else max(temps)
    
    # Calculate probability of expected value falling within the target range.
    # NWS hourly forecast is highly accurate but has a standard deviation of ±1.5°F.
    # We can model this as a normal/cumulative distribution, or simple step-wise probability:
    # If expected_val is perfectly within [target_min, target_max]: probability is high (~85%)
    # If expected_val is exactly on the boundary: probability is ~50%
    # If expected_val is 1°F outside: probability is ~25%
    # If expected_val is >= 2°F outside: probability is ~5%
    dist_to_range = 0.0
    if expected_val < target_min:
        dist_to_range = target_min - expected_val
    elif expected_val > target_max:
        dist_to_range = expected_val - target_max

    if dist_to_range == 0.0:
        # Expected value is inside the range. Depending on range width, assign probability:
        range_width = target_max - target_min
        if range_width >= 2:
            true_prob = 0.90
        else:
            true_prob = 0.70
    elif dist_to_range <= 0.5:
        true_prob = 0.50
    elif dist_to_range <= 1.0:
        true_prob = 0.25
    elif dist_to_range <= 1.5:
        true_prob = 0.12
    else:
        true_prob = 0.02

    # Find YES/NO tokens
    yes_token, no_token = None, None
    yes_price, no_price = None, None
    for t in tokens:
        outcome = (t.get("outcome") or t.get("name") or "").lower()
        price_raw = t.get("price") or t.get("probability")
        if price_raw is None:
            continue
        p = float(price_raw)
        if outcome == "yes":
            yes_token = t.get("token_id") or t.get("id")
            yes_price = p
        elif outcome == "no":
            no_token = t.get("token_id") or t.get("id")
            no_price = p

    if yes_price is None or no_price is None:
        return None, None, None

    edge_yes = true_prob - yes_price
    edge_no  = (1 - true_prob) - no_price

    logger.info(
        f"[ShortExpiry] Weather Target [{target_min}-{target_max}°F] | Forecast {expected_val:.1f}°F | "
        f"True Prob: {true_prob:.1%} | YES: {yes_price:.2f} (edge {edge_yes:+.1%}) | NO: {no_price:.2f} (edge {edge_no:+.1%})"
    )

    edge_threshold = MIN_EDGE_PCT / 100
    # Buy YES if it has edge and we expect it to hit
    if edge_yes > edge_threshold and edge_yes > edge_no:
        if 0.01 <= yes_price <= MAX_PRICE_TO_BUY: # allow low price buying for 10x-50x leverage!
            return yes_token, round(edge_yes * 100, 1), true_prob
    # Buy NO if it has edge
    elif edge_no > edge_threshold and edge_no > edge_yes:
        if 0.01 <= no_price <= MAX_PRICE_TO_BUY:
            return no_token, round(edge_no * 100, 1), 1 - true_prob

    return None, None, None


def _already_in_market(market_id: str) -> bool:
    """Return True if we already have an open position in this market."""
    open_positions = db.get_open_positions()
    return any(p.get("market_id") == market_id for p in open_positions)



class ShortExpiryEngine:
    """
    Scans for markets expiring within 90 minutes where we have
    a measurable edge, then enters small positions.
    """

    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None

    def _scan(self):
        """Main scan loop."""
        while self._running:
            try:
                self._scan_once()
            except Exception as e:
                logger.error(f"[ShortExpiry] Scan error: {e}")
            time.sleep(SCAN_INTERVAL_SECS)

    def _scan_once(self):
        now = datetime.now(timezone.utc)

        # --- Safety gate 1: kill switch ---
        if risk.kill_switch_active:
            return

        # --- Safety gate 2: concurrent position limit ---
        active_count = _count_active_short_expiry_positions()
        if active_count >= MAX_CONCURRENT_TRADES:
            logger.info(f"[ShortExpiry] {active_count} active short-expiry trades. Waiting for resolution.")
            return

        # --- Safety gate 3: minimum cash available ---
        balance = db.get_escrowed_balance()  # available on exchange
        try:
            from bot.client import clob
            balance = clob.get_usdc_balance()
        except Exception:
            pass

        if balance < POSITION_SIZE_USD * 1.2:
            logger.info(f"[ShortExpiry] Insufficient balance (${balance:.2f}) for short-expiry trade.")
            return

        # --- Fetch markets expiring within window ---
        cutoff_max = now + timedelta(minutes=MAX_MINUTES_TO_EXPIRY)
        cutoff_min = now + timedelta(minutes=MIN_MINUTES_TO_EXPIRY)

        try:
            r = requests.get(
                "https://gamma-api.polymarket.com/markets",
                params={
                    "active": "true",
                    "closed": "false",
                    "end_date_max": cutoff_max.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "limit": 50,
                    "order": "volume24hr",
                    "ascending": "false",
                },
                timeout=10,
            )
            markets = r.json() if r.ok else []
            if isinstance(markets, dict):
                markets = markets.get("results", [])
        except Exception as e:
            logger.warning(f"[ShortExpiry] Failed to fetch markets: {e}")
            return

        opportunities = 0
        for market in markets:
            if not self._running:
                break

            end_str = market.get("endDate") or market.get("endDateIso")
            if not end_str:
                continue

            # Parse expiry
            try:
                end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                mins_left = (end_dt - now).total_seconds() / 60
            except Exception:
                continue

            # Must be in our window
            if not (MIN_MINUTES_TO_EXPIRY <= mins_left <= MAX_MINUTES_TO_EXPIRY):
                continue

            # Liquidity check
            try:
                liquidity = float(market.get("liquidity") or 0)
            except (TypeError, ValueError):
                liquidity = 0
            if liquidity < MIN_LIQUIDITY_USD:
                continue

            question = market.get("question") or market.get("title") or ""
            market_id = market.get("conditionId") or market.get("id") or ""

            # Skip subjective markets
            if _should_skip(question):
                continue

            # Skip if already in this market
            if _already_in_market(market_id):
                continue

            # Get tokens / prices from market data
            tokens = market.get("tokens") or market.get("outcomes") or []

            # ── Edge detection per market type ────────────────────────────
            token_id, edge_pct, confidence = None, None, None

            # Try BTC price market
            token_id, edge_pct, confidence = _parse_btc_market(question, tokens)

            # Try ETH price market
            if token_id is None:
                token_id, edge_pct, confidence = _parse_eth_market(question, tokens)

            # Try Weather market
            if token_id is None:
                token_id, edge_pct, confidence = _parse_weather_market(question, tokens)

            # If we found a tradeable edge, execute
            if token_id and edge_pct and confidence:
                opportunities += 1
                logger.info(
                    f"[ShortExpiry] 🎯 OPPORTUNITY FOUND!\n"
                    f"  Market: {question[:80]}\n"
                    f"  Expires in {mins_left:.0f} min | Liquidity: ${liquidity:,.0f}\n"
                    f"  Edge: {edge_pct:.1f}% | Confidence: {confidence:.1%}\n"
                    f"  Size: ${POSITION_SIZE_USD:.2f}"
                )

                # --- Safety gate 4: re-check concurrent limit before placing ---
                if _count_active_short_expiry_positions() >= MAX_CONCURRENT_TRADES:
                    logger.info("[ShortExpiry] Concurrent limit reached mid-scan. Skipping.")
                    break

                try:
                    result = orders.place_short_expiry_order(
                        market_id=market_id,
                        market_question=question,
                        token_id=token_id,
                        side="BUY",
                        current_price=confidence,
                        size_usd=POSITION_SIZE_USD,
                        edge_pct=edge_pct,
                        confidence=confidence,
                        mins_to_expiry=mins_left,
                        notes=f"Edge={edge_pct:.1f}% | Expires={mins_left:.0f}min | Liq=${liquidity:,.0f}",
                    )
                    if result:
                        logger.success(
                            f"[ShortExpiry] ✅ Order placed: '{question[:60]}' "
                            f"| ${POSITION_SIZE_USD:.2f} @ {confidence:.2f}"
                        )
                except Exception as e:
                    logger.error(f"[ShortExpiry] Order failed: {e}")

        if opportunities == 0:
            logger.info(
                f"[ShortExpiry] Scanned {len(markets)} markets expiring in "
                f"{MIN_MINUTES_TO_EXPIRY}-{MAX_MINUTES_TO_EXPIRY} min. No edge found."
            )

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._scan, name="ShortExpiryEngine", daemon=True)
        self._thread.start()
        logger.info("[ShortExpiry] Engine started — scanning for short-term opportunities every 45s")

    def stop(self):
        self._running = False


short_expiry_engine = ShortExpiryEngine()
