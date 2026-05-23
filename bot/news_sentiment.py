"""
bot/news_sentiment.py — AI-driven news sentiment arbitrage strategy.
Scrapes news headlines, uses Gemini to predict outcomes, and trades discrepancies.
"""
import time
import threading
import urllib.parse
import xml.etree.ElementTree as ET
import requests
from loguru import logger

from bot import config
from bot import database as db
from bot.client import gamma, clob
from bot.order_manager import orders
from bot.risk_manager import risk


class NewsSentimentEngine:
    def __init__(self):
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

    def get_news_headlines(self, query: str, limit: int = 8) -> list[str]:
        """Fetch latest headlines from Google News RSS feed."""
        encoded_query = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                return []
            root = ET.fromstring(resp.content)
            headlines = []
            for item in root.findall(".//item")[:limit]:
                title = item.find("title")
                if title is not None and title.text:
                    # Clean up Google News title format (ends with " - Publisher")
                    headline = title.text
                    if " - " in headline:
                        headline = " - ".join(headline.split(" - ")[:-1])
                    headlines.append(headline.strip())
            return headlines
        except Exception as e:
            logger.error(f"[News] Error fetching news for query '{query}': {e}")
            return []

    def analyze_sentiment(self, question: str, headlines: list[str]) -> dict:
        """Query Gemini API (or run simulator) to determine implied probability."""
        if not headlines:
            return {
                "probability": 0.5,
                "sentiment": "neutral",
                "reasoning": "No headlines found to analyze.",
                "confidence": 0.0
            }

        if not config.AI_SCORING_ENABLED or not config.GEMINI_API_KEY:
            # Simulated AI Analysis for dry-run/development mode
            import random
            # Deterministic pseudo-randomness based on question hash to make it steady
            q_hash = sum(ord(c) for c in question)
            random.seed(q_hash + int(time.time() // 3600)) # rotates every hour
            
            prob = round(random.uniform(0.20, 0.80), 2)
            sentiment = "positive" if prob > 0.55 else ("negative" if prob < 0.45 else "neutral")
            confidence = round(random.uniform(0.65, 0.88), 2)
            
            # Reset random seed
            random.seed()
            
            return {
                "probability": prob,
                "sentiment": sentiment,
                "reasoning": f"[SIMULATED AI] Analyzed {len(headlines)} headlines. General sentiment is {sentiment} with stable consensus.",
                "confidence": confidence
            }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={config.GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        
        prompt = f"""You are an expert prediction market analyst.
Analyze the following news headlines related to the prediction market: "{question}"
Estimate the probability of this event resolving to "YES" on a scale from 0.0 to 1.0.

Headlines:
{chr(10).join(f'- {h}' for h in headlines)}

Your output must be a valid JSON object with the following fields:
- "probability": float (between 0.0 and 1.0 representing the true probability of YES outcome)
- "sentiment": "positive", "negative", or "neutral"
- "reasoning": string (brief description of your logic, max 120 chars)
- "confidence": float (between 0.0 and 1.0)

Do not include any markdown formatting or extra text outside the JSON. Return only the JSON object."""

        data = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "responseMimeType": "application/json"
            }
        }
        
        try:
            resp = requests.post(url, headers=headers, json=data, timeout=15)
            resp.raise_for_status()
            result = resp.json()
            
            candidates = result.get("candidates", [])
            if candidates:
                text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "{}")
                import json
                parsed = json.loads(text.strip())
                return {
                    "probability": float(parsed.get("probability", 0.5)),
                    "sentiment": parsed.get("sentiment", "neutral").lower(),
                    "reasoning": parsed.get("reasoning", "No reasoning provided."),
                    "confidence": float(parsed.get("confidence", 0.5))
                }
        except Exception as e:
            logger.error(f"[News] Gemini API error: {e}")
            
        return {
            "probability": 0.5,
            "sentiment": "neutral",
            "reasoning": f"Gemini API analysis failed: {str(e)[:50]}",
            "confidence": 0.0
        }

    def _scan_and_trade(self):
        logger.info("[News] Scanning active markets for news sentiment arbitrage…")
        try:
            # Scan active Politics or general high volume markets
            markets = gamma.get_active_markets(limit=15, min_volume=10000)
            if not markets:
                markets = gamma.get_active_markets(limit=10, min_volume=1000)

            for m in markets:
                if not self._running:
                    break

                market_id = m.get("conditionId")
                if not market_id:
                    continue

                # Skip if position already open
                if db.position_exists(market_id):
                    continue

                question = m.get("question") or m.get("title") or market_id
                
                # Fetch news headlines
                headlines = self.get_news_headlines(question)
                if not headlines:
                    continue

                # Analyze
                analysis = self.analyze_sentiment(question, headlines)
                predicted_prob = analysis["probability"]
                sentiment = analysis["sentiment"]

                # Log analysis event to DB for dashboard display
                db.log_event(
                    "news",
                    f"AI Score for '{question[:40]}...': {predicted_prob*100:.1f}% ({sentiment})",
                    severity="info",
                    data={
                        "market_id": market_id,
                        "question": question,
                        "probability": predicted_prob,
                        "sentiment": sentiment,
                        "reasoning": analysis["reasoning"],
                        "confidence": analysis["confidence"],
                        "headlines": headlines[:3]
                    }
                )

                # Get YES price (implied probability)
                implied_prob = gamma.get_implied_probability(m, "Yes")
                if not implied_prob:
                    continue

                # Evaluate trade condition: discrepancy >= 15%
                diff = predicted_prob - implied_prob
                
                if abs(diff) >= 0.15:
                    side = "BUY"
                    # If Gemini probability is higher, buy YES. If lower, buy NO.
                    outcome = "Yes" if diff > 0 else "No"
                    token_id = gamma.get_token_id_for_outcome(m, outcome)
                    if not token_id:
                        continue

                    market_price = implied_prob if outcome == "Yes" else (1.0 - implied_prob)

                    logger.info(
                        f"[News] Arbitrage found on '{question[:30]}': AI prob {predicted_prob:.2f} "
                        f"vs market {implied_prob:.2f}. Trading {outcome}..."
                    )

                    orders.place_sentiment_trade(
                        market_id=market_id,
                        market_question=question,
                        token_id=token_id,
                        side=side,
                        outcome=outcome,
                        current_price=market_price,
                        size_usd=config.POSITION_SIZE_USD,
                        ai_prob=predicted_prob
                    )
                    
                    time.sleep(1) # rate limit pace

        except Exception as e:
            logger.error(f"[News] Scan error: {e}")

    def _run(self):
        logger.info("[News] Sentiment Engine thread running")
        while self._running:
            self._scan_and_trade()
            
            # Sleep for 15 minutes between scans
            for _ in range(900):
                if not self._running:
                    break
                time.sleep(1)
                
        logger.info("[News] Sentiment Engine thread stopped")

    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._run, name="NewsSentiment", daemon=True)
            self._thread.start()
            logger.info("[News] Sentiment Engine started")

    def stop(self):
        with self._lock:
            self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            logger.info("[News] Sentiment Engine stopped")


news_engine = NewsSentimentEngine()
