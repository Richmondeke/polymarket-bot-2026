"""
bot/client.py — Polymarket API wrapper.
Wraps CLOB API (trading), Data API (leaderboard/positions), and Gamma API (markets).
All methods handle rate limiting and return clean Python dicts.
"""
import time
import threading
from typing import Optional, List, Dict, Any, Tuple
from loguru import logger
import requests

from bot import config

# ── Rate limiter ────────────────────────────────────────────────────

class _RateLimiter:
    """Simple token-bucket rate limiter."""
    def __init__(self, calls_per_second: float = 2.0):
        self._min_interval = 1.0 / calls_per_second
        self._last_call = 0.0
        self._lock = threading.Lock()

    def wait(self):
        with self._lock:
            now = time.monotonic()
            wait_time = self._min_interval - (now - self._last_call)
            if wait_time > 0:
                time.sleep(wait_time)
            self._last_call = time.monotonic()


_gamma_limiter = _RateLimiter(calls_per_second=3.0)
_data_limiter = _RateLimiter(calls_per_second=1.0)   # stricter limit on Data API
_clob_limiter = _RateLimiter(calls_per_second=5.0)


def _get(url: str, params: Dict = None, limiter: _RateLimiter = None, retries: int = 3) -> Optional[Dict]:
    """HTTP GET with retry and rate limiting."""
    if limiter:
        limiter.wait()
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 429:
                wait = 2 ** attempt
                logger.warning(f"[Client] Rate limited. Waiting {wait}s… (attempt {attempt+1})")
                time.sleep(wait)
            else:
                logger.error(f"[Client] HTTP {resp.status_code} for {url}: {e}")
                return None
        except Exception as e:
            logger.error(f"[Client] Request error ({attempt+1}/{retries}): {e}")
            time.sleep(1)
    return None


# ── CLOB Client (authenticated trading) ─────────────────────────────

class ClobClientWrapper:
    """
    Wraps py_clob_client_v2 for authenticated order operations.
    Falls back gracefully if credentials are not configured.
    """
    def __init__(self):
        self._client = None
        self._initialized = False
        self._init_lock = threading.Lock()
        self._virtual_balance = 100.0

    def _init(self):
        with self._init_lock:
            if self._initialized:
                return
            if not config.POLYGON_PRIVATE_KEY:
                logger.warning("[CLOB] No private key — running in read-only mode")
                self._initialized = True
                return
            try:
                from py_clob_client import ClobClient, ApiCreds
                creds = None
                if config.POLY_API_KEY:
                    creds = ApiCreds(
                        api_key=config.POLY_API_KEY,
                        api_secret=config.POLY_API_SECRET,
                        api_passphrase=config.POLY_API_PASSPHRASE,
                    )
                self._client = ClobClient(
                    host=config.CLOB_HOST,
                    chain_id=config.CHAIN_ID,
                    key=config.POLYGON_PRIVATE_KEY,
                    creds=creds,
                )
                if not creds:
                    logger.info("[CLOB] Deriving API credentials from private key…")
                    derived = self._client.create_or_derive_api_key()
                    self._client = ClobClient(
                        host=config.CLOB_HOST,
                        chain_id=config.CHAIN_ID,
                        key=config.POLYGON_PRIVATE_KEY,
                        creds=derived,
                    )
                    logger.info("[CLOB] API credentials derived successfully")
                logger.info("[CLOB] Client initialized ✓")
            except ImportError:
                logger.warning("[CLOB] py_clob_client_v2 not installed. Run: pip install py_clob_client_v2")
            except Exception as e:
                logger.error(f"[CLOB] Failed to initialize: {e}")
            finally:
                self._initialized = True

    @property
    def client(self):
        if not self._initialized:
            self._init()
        return self._client

    def get_order_book(self, token_id: str) -> Optional[Dict]:
        """Get current order book for a token."""
        _clob_limiter.wait()
        try:
            if self.client:
                return self.client.get_order_book(token_id)
            # Fallback: public REST
            data = _get(f"{config.CLOB_HOST}/book", {"token_id": token_id}, _clob_limiter)
            return data
        except Exception as e:
            logger.error(f"[CLOB] get_order_book error: {e}")
            return None

    def get_best_ask(self, token_id: str) -> Optional[float]:
        """Return the current best ask price (0-1 scale)."""
        book = self.get_order_book(token_id)
        if not book:
            if config.DRY_RUN:
                import random
                return round(random.uniform(0.70, 0.90), 2)
            return None
        try:
            asks = book.get("asks", [])
            if asks:
                return float(asks[0]["price"])
        except Exception:
            pass
        return None

    def get_usdc_balance(self) -> float:
        """Return current USDC balance from Polygon wallet."""
        if config.DRY_RUN:
            return self._virtual_balance
        if not self.client:
            return 0.0
        try:
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(config.POLYGON_RPC_URL))
            abi = [{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]
            wallet = w3.to_checksum_address(config.POLYGON_WALLET_ADDRESS)
            
            # Check Bridged USDC (USDC.e)
            usdc_e = w3.eth.contract(address=w3.to_checksum_address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"), abi=abi)
            bal_e = usdc_e.functions.balanceOf(wallet).call()
            
            # Check Native USDC
            usdc_n = w3.eth.contract(address=w3.to_checksum_address("0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"), abi=abi)
            bal_n = usdc_n.functions.balanceOf(wallet).call()
            
            return (float(bal_e) + float(bal_n)) / 10**6
        except Exception as e:
            logger.error(f"[CLOB] get_usdc_balance error: {e}")
            return 0.0

    def place_limit_order(
        self,
        token_id: str,
        side: str,
        price: float,
        size_shares: float,
        tick_size: str = "0.01",
        post_only: bool = False,
    ) -> Optional[Dict]:
        """Place a limit order. Returns order response dict."""
        if config.DRY_RUN:
            logger.info(f"[CLOB] 🟡 DRY RUN — would place {side} limit @ {price:.3f} for {size_shares:.2f} shares (post_only={post_only})")
            # Update virtual balance for dry-run simulation
            cost = price * size_shares
            if side.upper() == "BUY":
                self._virtual_balance = max(0.0, self._virtual_balance - cost)
            else:
                self._virtual_balance += cost
            return {"dry_run": True, "order_id": f"dry-{int(time.time())}", "status": "simulated"}

        if not self.client:
            logger.error("[CLOB] Cannot place order — client not initialized")
            return None

        _clob_limiter.wait()
        try:
            from py_clob_client.clob_types import OrderArgs, PartialCreateOrderOptions
            from py_clob_client.order_builder.constants import BUY, SELL

            resp = self.client.create_and_post_order(
                order_args=OrderArgs(
                    token_id=token_id,
                    price=round(price, 4),
                    side=BUY if side.upper() == "BUY" else SELL,
                    size=size_shares,
                ),
                options=PartialCreateOrderOptions(tick_size=tick_size),
            )
            logger.info(f"[CLOB] ✅ Order placed: {resp}")
            return resp
        except Exception as e:
            logger.error(f"[CLOB] place_limit_order error: {e}")
            from bot import database as db
            db.log_event("error", f"[CLOB] place_limit_order error: {e}", severity="error")
            return None

    def cancel_order(self, order_id: str) -> bool:
        if config.DRY_RUN:
            logger.info(f"[CLOB] 🟡 DRY RUN — would cancel order {order_id}")
            return True
        if not self.client:
            return False
        try:
            _clob_limiter.wait()
            self.client.cancel_order(order_id)
            return True
        except Exception as e:
            logger.error(f"[CLOB] cancel_order error: {e}")
            return False

    def cancel_all_orders(self) -> bool:
        if config.DRY_RUN:
            logger.info("[CLOB] 🟡 DRY RUN — would cancel all orders")
            return True
        if not self.client:
            return False
        try:
            _clob_limiter.wait()
            self.client.cancel_all_orders()
            logger.info("[CLOB] 🔴 All open orders cancelled (KILL SWITCH)")
            return True
        except Exception as e:
            logger.error(f"[CLOB] cancel_all_orders error: {e}")
            return False

    def get_open_orders(self) -> List[Dict]:
        if not self.client:
            return []
        try:
            _clob_limiter.wait()
            orders = self.client.get_orders()
            return orders or []
        except Exception as e:
            logger.error(f"[CLOB] get_open_orders error: {e}")
            return []


# ── Gamma API (market discovery) ────────────────────────────────────

class GammaClient:
    """Wraps the Polymarket Gamma API for market metadata."""

    def get_active_markets(
        self,
        category: str = None,
        limit: int = 100,
        min_volume: float = 10000,
    ) -> List[Dict]:
        """Fetch active markets, optionally filtered by category."""
        params = {
            "active": "true",
            "closed": "false",
            "limit": limit,
        }
        if category:
            params["tag"] = category

        data = _get(f"{config.GAMMA_HOST}/markets", params, _gamma_limiter)
        if not data:
            return []

        markets = data if isinstance(data, list) else data.get("results", [])
        # Filter by minimum volume
        return [m for m in markets if float(m.get("volume", 0)) >= min_volume]

    def get_market(self, condition_id: str) -> Optional[Dict]:
        """Fetch a specific market by condition ID."""
        data = _get(f"{config.GAMMA_HOST}/markets/{condition_id}", limiter=_gamma_limiter)
        return data

    def get_events(self, category: str = None, limit: int = 50) -> List[Dict]:
        """Fetch events (groups of related markets)."""
        params = {"limit": limit, "active": "true"}
        if category:
            params["tag"] = category
        data = _get(f"{config.GAMMA_HOST}/events", params, _gamma_limiter)
        if not data:
            return []
        return data if isinstance(data, list) else data.get("results", [])

    def get_token_id_for_outcome(self, market: Dict, outcome: str = "Yes") -> Optional[str]:
        """Extract token_id for a specific outcome (Yes/No)."""
        try:
            clob_token_ids = market.get("clobTokenIds")
            if clob_token_ids:
                if isinstance(clob_token_ids, str):
                    import json
                    try:
                        ids = json.loads(clob_token_ids)
                    except:
                        # try to fix single quotes
                        ids = json.loads(clob_token_ids.replace("'", "\""))
                elif isinstance(clob_token_ids, list):
                    ids = clob_token_ids
                else:
                    ids = []

                if isinstance(ids, list) and len(ids) > 1:
                    return ids[0] if outcome.lower() == "yes" else ids[1]
                elif isinstance(ids, list) and len(ids) > 0:
                    return ids[0]

            tokens = market.get("tokens", [])
            for token in tokens:
                if isinstance(token, dict) and token.get("outcome", "").lower() == outcome.lower():
                    return token.get("token_id")
        except Exception as e:
            logger.error(f"Error parsing token_id for {market.get('id')}: {e}")
        return None

    def get_implied_probability(self, market: Dict, outcome: str = "Yes") -> Optional[float]:
        """Get implied probability for an outcome from market data."""
        try:
            prices_str = market.get("outcomePrices")
            if prices_str:
                if isinstance(prices_str, str):
                    import json
                    try:
                        prices = json.loads(prices_str)
                    except:
                        prices = json.loads(prices_str.replace("'", "\""))
                elif isinstance(prices_str, list):
                    prices = prices_str
                else:
                    prices = []

                if isinstance(prices, list) and len(prices) > 1:
                    return float(prices[0]) if outcome.lower() == "yes" else float(prices[1])
                elif isinstance(prices, list) and len(prices) > 0:
                    return float(prices[0])

            tokens = market.get("tokens", [])
            for token in tokens:
                if isinstance(token, dict) and token.get("outcome", "").lower() == outcome.lower():
                    return float(token.get("price", 0.0))
        except Exception as e:
            logger.error(f"Error parsing implied prob for {market.get('id')}: {e}")
        return None


# ── Data API (leaderboard, positions, trades) ────────────────────────

class DataClient:
    """Wraps the Polymarket Data API for analytics and user data."""

    def get_leaderboard(self, limit: int = 50) -> List[Dict]:
        """Fetch top traders from the leaderboard."""
        data = _get(
            f"{config.DATA_HOST}/leaderboard",
            {"limit": limit, "window": "allTime"},
            _data_limiter,
        )
        if not data:
            return []
        return data if isinstance(data, list) else data.get("data", [])

    def get_user_trades(
        self,
        proxy_address: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict]:
        """Fetch recent trades for a specific wallet (proxy address)."""
        data = _get(
            f"{config.DATA_HOST}/trades",
            {
                "user": proxy_address,
                "limit": limit,
                "offset": offset,
            },
            _data_limiter,
        )
        if not data:
            return []
        return data if isinstance(data, list) else data.get("data", [])

    def get_user_positions(self, proxy_address: str) -> List[Dict]:
        """Fetch open positions for a wallet."""
        data = _get(
            f"{config.DATA_HOST}/positions",
            {"user": proxy_address},
            _data_limiter,
        )
        if not data:
            return []
        return data if isinstance(data, list) else data.get("data", [])

    def get_user_pnl(self, proxy_address: str) -> Optional[Dict]:
        """Get realized P&L summary for a wallet."""
        data = _get(
            f"{config.DATA_HOST}/profile",
            {"address": proxy_address},
            _data_limiter,
        )
        return data

    def get_recent_large_trades(
        self,
        min_usd: float = 1000,
        limit: int = 100,
    ) -> List[Dict]:
        """Fetch recent large trades across all markets."""
        data = _get(
            f"{config.DATA_HOST}/trades",
            {"limit": limit},
            _data_limiter,
        )
        if not data:
            return []
        trades = data if isinstance(data, list) else data.get("data", [])
        return [t for t in trades if float(t.get("usdcSize", 0)) >= min_usd]


# ── Singleton instances ──────────────────────────────────────────────

clob = ClobClientWrapper()
gamma = GammaClient()
data_api = DataClient()
