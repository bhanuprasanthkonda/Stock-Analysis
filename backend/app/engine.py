import numpy as np
import pandas as pd
from typing import Optional
import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer

nltk.download('vader_lexicon', quiet=True)
_vader = SentimentIntensityAnalyzer()


def calculate_sma(closes: list[float], period: int) -> list[Optional[float]]:
    """Simple moving average over `period` closes.
    Returns None for the first (period-1) positions so the output length
    always matches the input — callers can zip it with OHLCV timestamps safely.
    """
    result: list[Optional[float]] = [None] * (period - 1)
    for i in range(period - 1, len(closes)):
        result.append(round(float(np.mean(closes[i - period + 1 : i + 1])), 4))
    return result


def calculate_ema(closes: list[float], period: int) -> list[Optional[float]]:
    """Exponential moving average seeded with the SMA of the first `period` values.
    Seeding with SMA (instead of the first price) avoids the cold-start spike that
    occurs when a single extreme price dominates the early EMA. Returns None for
    the first (period-1) positions to align with the SMA output shape.
    """
    if len(closes) < period:
        return [None] * len(closes)

    multiplier = 2 / (period + 1)
    result: list[Optional[float]] = [None] * (period - 1)

    # Seed with SMA of first `period` values
    seed = float(np.mean(closes[:period]))
    result.append(round(seed, 4))

    for price in closes[period:]:
        prev = result[-1]
        result.append(round(price * multiplier + prev * (1 - multiplier), 4))

    return result


def calculate_fibonacci(high: float, low: float) -> dict[str, float]:
    """Compute the 7 standard Fibonacci retracement levels between `high` and `low`.
    Levels are measured from the high downward (high = 0%, low = 100%).
    Keys are percentage strings (e.g. '23.6', '61.8').
    """
    diff = high - low
    levels = [0.0, 0.236, 0.382, 0.500, 0.618, 0.786, 1.0]
    return {
        str(int(lvl * 100)) if lvl in (0.0, 1.0) else f"{lvl * 100:.1f}": round(high - diff * lvl, 4)
        for lvl in levels
    }


def extract_ohlcv(df: pd.DataFrame) -> list[dict]:
    """Convert a yfinance history DataFrame to a list of OHLCV dicts.
    Timestamps are stored as Unix seconds (int) — not date strings — so
    lightweight-charts can handle both daily and intraday data with one code path.
    """
    records = []
    for ts, row in df.iterrows():
        records.append({
            "date": int(ts.timestamp()),  # Unix seconds — works for daily + intraday
            "open": round(float(row["Open"]), 4),
            "high": round(float(row["High"]), 4),
            "low": round(float(row["Low"]), 4),
            "close": round(float(row["Close"]), 4),
            "volume": int(row["Volume"]),
        })
    return records


def get_60day_high_low(df: pd.DataFrame) -> tuple[float, float]:
    """Return the (high, low) over the last 60 candles.
    Used as the reference range for Fibonacci level calculation.
    """
    last_60 = df.tail(60)
    return float(last_60["High"].max()), float(last_60["Low"].min())


# ── Sentiment ────────────────────────────────────────────────────────────────

def score_headline(text: str) -> tuple[str, float]:
    """Run VADER sentiment analysis on a single headline.
    Returns a (label, compound_score) tuple.
    Thresholds: compound >= 0.05 → 'good', <= -0.05 → 'bad', else 'neutral'.
    """
    compound = _vader.polarity_scores(text)["compound"]
    if compound >= 0.05:
        label = "good"
    elif compound <= -0.05:
        label = "bad"
    else:
        label = "neutral"
    return label, round(compound, 4)


# ── Signal Engine ─────────────────────────────────────────────────────────────

def calculate_signals(
    current_price: float,
    sma_20_last: Optional[float],
    sma_50_last: Optional[float],
    ema_20_last: Optional[float],
    ema_50_last: Optional[float],
    news_sentiments: list[str],
    closes: list[float],
    volumes: list[int],
) -> dict:
    """Composite signal engine combining technical, sentiment, and volume factors.

    Weighting: technical indicators 50%, news sentiment 35%, volume signal 15%.
    Each technical sub-signal is binary (0 = bearish, 100 = bullish); their average
    forms the tech score. The composite is mapped to Buy / Sell / Hold percentages
    where Hold peaks at 50 (maximum uncertainty) and falls toward extremes.

    Returns a dict with keys: buy, sell, hold (percentages), breakdown (detail map).
    """
    breakdown: dict = {}
    tech_signals: list[float] = []

    # Technical indicators — each 0 (bearish) or 100 (bullish)
    if sma_20_last and current_price:
        bull = current_price > sma_20_last
        tech_signals.append(100.0 if bull else 0.0)
        breakdown["price_vs_sma20"] = "bullish" if bull else "bearish"

    if sma_50_last and current_price:
        bull = current_price > sma_50_last
        tech_signals.append(100.0 if bull else 0.0)
        breakdown["price_vs_sma50"] = "bullish" if bull else "bearish"

    if sma_20_last and sma_50_last:
        bull = sma_20_last > sma_50_last
        tech_signals.append(100.0 if bull else 0.0)
        breakdown["sma_cross"] = "golden" if bull else "death"

    if ema_20_last and ema_50_last:
        bull = ema_20_last > ema_50_last
        tech_signals.append(100.0 if bull else 0.0)
        breakdown["ema_cross"] = "golden" if bull else "death"

    tech_score = sum(tech_signals) / len(tech_signals) if tech_signals else 50.0

    # News sentiment — (good - bad) ratio mapped from [-1, 1] to [0, 100]
    good = sum(1 for s in news_sentiments if s == "good")
    bad = sum(1 for s in news_sentiments if s == "bad")
    total_news = len(news_sentiments)
    if total_news:
        sentiment_score = ((good - bad) / total_news) * 50 + 50  # 0-100
    else:
        sentiment_score = 50.0
    breakdown["news_good"] = good
    breakdown["news_bad"] = bad
    breakdown["news_neutral"] = total_news - good - bad

    # Volume signal — elevated volume (>15% above avg) confirms price direction
    vol_score = 50.0
    if len(volumes) >= 20 and len(closes) >= 6:
        avg_vol = sum(volumes) / len(volumes)
        recent_vol = sum(volumes[-5:]) / 5
        price_up = closes[-1] > closes[-5]
        if recent_vol > avg_vol * 1.15:
            vol_score = 72.0 if price_up else 28.0
            breakdown["volume"] = "elevated_bullish" if price_up else "elevated_bearish"
        else:
            breakdown["volume"] = "normal"
    else:
        breakdown["volume"] = "insufficient_data"

    # Composite bull score (0-100): tech 50%, sentiment 35%, volume 15%
    composite = tech_score * 0.50 + sentiment_score * 0.35 + vol_score * 0.15
    breakdown["composite"] = round(composite, 1)
    breakdown["tech_score"] = round(tech_score, 1)
    breakdown["sentiment_score"] = round(sentiment_score, 1)
    breakdown["volume_score"] = round(vol_score, 1)

    # Map composite → Buy / Sell / Hold
    # Hold peaks at composite=50 (full uncertainty) and falls toward extremes
    buy_raw = composite
    sell_raw = 100 - composite
    hold_raw = 100 - abs(composite - 50)
    total = buy_raw + sell_raw + hold_raw

    buy_pct = round(buy_raw / total * 100, 1)
    sell_pct = round(sell_raw / total * 100, 1)
    hold_pct = round(100 - buy_pct - sell_pct, 1)

    return {"buy": buy_pct, "sell": sell_pct, "hold": hold_pct, "breakdown": breakdown}
