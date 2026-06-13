import yfinance as yf
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, engine as eng

router = APIRouter(prefix="/stocks", tags=["stocks"])


# ── Ticker / company search (must be before /{ticker} to avoid shadowing) ─────

@router.get("/search", response_model=list[schemas.TickerSearchResult])
def search_stocks(q: str = Query(..., min_length=1)):
    try:
        results = yf.Search(q, max_results=8)
        quotes = results.quotes or []
        return [
            schemas.TickerSearchResult(
                ticker=r.get("symbol", ""),
                name=r.get("longname") or r.get("shortname") or "",
            )
            for r in quotes if r.get("symbol")
        ]
    except Exception:
        return []


# UI period key → yfinance period string
_PERIOD_TO_YF: dict[str, str] = {
    "1d": "1d", "1w": "5d", "1mo": "1mo", "3mo": "3mo",
    "6mo": "6mo", "ytd": "ytd", "1y": "1y", "2y": "2y",
    "5y": "5y", "max": "max",
}

_VALID_INTERVALS = {
    "1m", "2m", "5m", "15m", "30m", "60m", "1h", "1d", "5d", "1wk", "1mo", "3mo"
}


def _safe_float(val) -> float | None:
    try:
        v = float(val)
        return None if pd.isna(v) else round(v, 4)
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> int | None:
    try:
        v = int(val)
        return None if v == 0 else v
    except (TypeError, ValueError):
        return None


@router.get("/{ticker}", response_model=schemas.StockResponse)
def get_stock(
    ticker: str,
    period: str = Query("1y"),
    interval: str = Query("1d"),
    db: Session = Depends(get_db),
):
    ticker = ticker.upper().strip()
    yf_period   = _PERIOD_TO_YF.get(period, "1y")
    yf_interval = interval if interval in _VALID_INTERVALS else "1d"

    t = yf.Ticker(ticker)
    hist = t.history(period=yf_period, interval=yf_interval)

    if hist.empty:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found or no data available")

    info = t.info
    fast = t.fast_info

    company_name = info.get("longName") or info.get("shortName") or ticker
    # Replace any existing entry so this ticker floats to top with latest timestamp
    db.query(models.SearchHistory).filter(models.SearchHistory.ticker == ticker).delete()
    db.add(models.SearchHistory(ticker=ticker, company_name=company_name))
    db.commit()

    # OHLCV
    ohlcv = eng.extract_ohlcv(hist)
    closes = [c["close"] for c in ohlcv]

    # Indicators
    sma_20  = eng.calculate_sma(closes, 20)
    sma_50  = eng.calculate_sma(closes, 50)
    sma_200 = eng.calculate_sma(closes, 200)
    ema_20  = eng.calculate_ema(closes, 20)
    ema_50  = eng.calculate_ema(closes, 50)

    # Fibonacci (60-day high/low)
    high_60, low_60 = eng.get_60day_high_low(hist)
    fib_levels = eng.calculate_fibonacci(high_60, low_60)

    # Institutional holders
    holders: list[schemas.InstitutionalHolder] = []
    try:
        ih = t.institutional_holders
        if ih is not None and not ih.empty:
            for _, row in ih.iterrows():
                holders.append(schemas.InstitutionalHolder(
                    holder=str(row.get("Holder", "")),
                    shares=_safe_int(row.get("Shares")),
                    value=_safe_float(row.get("Value")),
                    pct_out=_safe_float(row.get("% Out")),
                    date_reported=str(row["Date Reported"].date()) if pd.notna(row.get("Date Reported")) else None,
                ))
    except Exception:
        pass

    return schemas.StockResponse(
        ticker=ticker,
        company_name=info.get("longName") or info.get("shortName") or ticker,
        current_price=_safe_float(fast.last_price),
        previous_close=_safe_float(info.get("previousClose")),
        day_high=_safe_float(fast.day_high),
        day_low=_safe_float(fast.day_low),
        day_volume=_safe_int(hist["Volume"].iloc[-1]),
        avg_volume=_safe_int(fast.three_month_average_volume),
        market_cap=_safe_int(fast.market_cap),
        week_52_high=_safe_float(fast.year_high),
        week_52_low=_safe_float(fast.year_low),
        ohlcv=ohlcv,
        sma_20=sma_20,
        sma_50=sma_50,
        sma_200=sma_200,
        ema_20=ema_20,
        ema_50=ema_50,
        fibonacci=schemas.FibonacciLevels(
            high_60d=round(high_60, 4),
            low_60d=round(low_60, 4),
            levels=fib_levels,
        ),
        institutional_holders=holders,
    )


# ── News endpoint ─────────────────────────────────────────────────────────────

def _parse_news(raw: list[dict]) -> list[schemas.NewsItem]:
    items = []
    for entry in raw:
        content = entry.get("content") or {}
        title = content.get("title", "").strip()
        if not title:
            continue
        sentiment, compound = eng.score_headline(title)
        provider = content.get("provider") or {}
        canonical = content.get("canonicalUrl") or {}
        finance = content.get("finance") or {}
        stock_tickers = finance.get("stockTickers") or []
        related = list({t.get("symbol", "").upper() for t in stock_tickers if t.get("symbol")})
        items.append(schemas.NewsItem(
            title=title,
            publisher=provider.get("displayName", ""),
            url=canonical.get("url", ""),
            published_at=content.get("pubDate", ""),
            sentiment=sentiment,
            compound_score=compound,
            related_tickers=related,
        ))
    return items


@router.get("/{ticker}/news", response_model=list[schemas.NewsItem])
def get_news(ticker: str):
    ticker = ticker.upper().strip()
    t = yf.Ticker(ticker)
    raw = t.news or []
    if not raw:
        raise HTTPException(status_code=404, detail=f"No news found for '{ticker}'")
    return _parse_news(raw)


# ── Signals endpoint ──────────────────────────────────────────────────────────

@router.get("/{ticker}/signals", response_model=schemas.SignalsResponse)
def get_signals(ticker: str):
    ticker = ticker.upper().strip()
    t = yf.Ticker(ticker)
    hist = t.history(period="6mo")

    if hist.empty:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found")

    closes = [round(float(v), 4) for v in hist["Close"].tolist()]
    volumes = [int(v) for v in hist["Volume"].tolist()]

    sma_20 = eng.calculate_sma(closes, 20)
    sma_50 = eng.calculate_sma(closes, 50)
    ema_20 = eng.calculate_ema(closes, 20)
    ema_50 = eng.calculate_ema(closes, 50)

    news_items = _parse_news(t.news or [])
    sentiments = [n.sentiment for n in news_items]

    result = eng.calculate_signals(
        current_price=closes[-1],
        sma_20_last=sma_20[-1],
        sma_50_last=sma_50[-1],
        ema_20_last=ema_20[-1],
        ema_50_last=ema_50[-1],
        news_sentiments=sentiments,
        closes=closes,
        volumes=volumes,
    )

    return schemas.SignalsResponse(
        ticker=ticker,
        buy=result["buy"],
        sell=result["sell"],
        hold=result["hold"],
        breakdown=result["breakdown"],
    )
