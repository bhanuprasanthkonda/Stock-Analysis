import re
import html as html_lib
import yfinance as yf
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo
from curl_cffi import requests as cf_requests
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, engine as eng

router = APIRouter(prefix="/stocks", tags=["stocks"])

# Regex to extract ticker symbol from ETFdb's HTML-encoded symbol column
# e.g. '<a href="/stock/NVDA/"><span class="caps">NVDA</span></a>' → 'NVDA'
_ETFDB_SYM_RE = re.compile(r'>([A-Z0-9.]+)</(?:span|a)>')


def _fetch_etfdb_holdings(ticker: str) -> list[schemas.ETFHolding]:
    """Fetch complete ETF holdings from ETFdb.com using their internal data_set API.

    Strategy:
    1. Load the ETFdb product page to extract the ETF's internal numeric ID (`by_etf`).
    2. Paginate the data_set JSON endpoint in chunks of 15 (ETFdb's fixed page size)
       using the `offset` parameter until all rows are collected.

    curl_cffi with `impersonate='chrome120'` is required to bypass Cloudflare.
    Returns [] on any error so the caller can fall back to yfinance gracefully.
    """
    try:
        page = cf_requests.get(
            f"https://etfdb.com/etf/{ticker}/",
            impersonate="chrome120", timeout=15,
        )
        # The page embeds the holdings table URL like:
        # /data_set/?tm=82240&cond={"by_etf":1272}&...
        # tm=82240 is constant across all ETFs; by_etf is the internal ETFdb ID.
        m = re.search(
            r'/data_set/\?tm=(\d+)&cond=\{\"by_etf\":(\d+)\}',
            html_lib.unescape(page.text),
        )
        if not m:
            return []
        tm, etf_id = m.group(1), m.group(2)

        holdings: list[schemas.ETFHolding] = []
        offset, page_size = 0, 15
        while True:
            url = (
                f"https://etfdb.com/data_set/?tm={tm}"
                f"&cond={{\"by_etf\":{etf_id}}}"
                f"&no_null_sort=true&count_by_id=&limit={page_size}&offset={offset}"
            )
            data = cf_requests.get(url, impersonate="chrome120", timeout=10).json()
            rows = data.get("rows", [])
            if not rows:
                break
            for row in rows:
                sym_m = _ETFDB_SYM_RE.search(row.get("symbol", ""))
                sym = sym_m.group(1) if sym_m else ""
                if not sym:
                    continue
                # Strip HTML tags from holding name
                name = re.sub(r"<[^>]+>", "", row.get("holding", "")).strip() or None
                # Weight arrives as "8.15%" — strip non-numeric chars before parsing
                w_str = re.sub(r"[^0-9.]", "", row.get("weight", "") or "")
                weight = float(w_str) if w_str else None
                holdings.append(schemas.ETFHolding(symbol=sym, name=name, weight=weight))
            offset += page_size
            if offset >= data.get("total", 0):
                break
        return holdings
    except Exception:
        return []


# ── Market ticker bar (must be before /{ticker} to avoid shadowing) ──────────

_ET = ZoneInfo("America/New_York")

# Each entry: (label_spot, sym_spot, label_futures, sym_futures)
# Gold, Bitcoin, Crude Oil are already futures/24-7 — their pairs are identical.
_MARKETS = [
    ("S&P 500",      "^GSPC",   "S&P Fut.",      "ES=F"),
    ("Dow 30",       "^DJI",    "Dow Fut.",       "YM=F"),
    ("Nasdaq",       "^IXIC",   "Nasdaq Fut.",    "NQ=F"),
    ("Russell 2000", "^RUT",    "Russell Fut.",   "RTY=F"),
    ("VIX",          "^VIX",    "VIX",            "^VIX"),
    ("Gold",         "GC=F",    "Gold",           "GC=F"),
    ("Bitcoin",      "BTC-USD", "Bitcoin",        "BTC-USD"),
    ("Crude Oil",    "CL=F",    "Crude Oil",      "CL=F"),
]


def _is_trading_hours() -> bool:
    """Return True if US markets (including extended hours) are active.
    Trading window: 7:00 AM – 8:00 PM ET, Monday–Friday.
    Outside this window futures tickers replace the cash indices.
    Uses America/New_York so DST is handled correctly.
    """
    now = datetime.now(_ET)
    if now.weekday() >= 5:   # Saturday=5, Sunday=6
        return False
    h = now.hour + now.minute / 60
    return 7.0 <= h < 20.0


def _fetch_market_item(label: str, sym: str, is_futures: bool) -> schemas.MarketItem | None:
    """Fetch price and daily change for a single market symbol using 5-day history.
    The previous close is taken from the second-to-last daily candle so the change
    reflects the session-over-session move, not just intraday movement.
    Returns None on any error so the caller can skip it gracefully.
    """
    try:
        hist = yf.Ticker(sym).history(period="5d", interval="1d")
        if hist.empty:
            return None
        closes = hist["Close"].dropna()
        if closes.empty:
            return None
        price = float(closes.iloc[-1])
        prev  = float(closes.iloc[-2]) if len(closes) >= 2 else price
        change     = round(price - prev, 4)
        change_pct = round((change / prev) * 100, 2) if prev else 0.0
        return schemas.MarketItem(
            label=label, ticker=sym,
            price=round(price, 2),
            change=change, change_pct=change_pct,
            is_futures=is_futures,
        )
    except Exception:
        return None


@router.get("/markets", response_model=list[schemas.MarketItem])
def get_markets():
    """Return price + daily change for 8 major market indices/commodities.
    During trading hours (7 AM–8 PM ET Mon–Fri) returns cash indices (^GSPC etc.).
    Outside that window switches to E-mini futures (ES=F, YM=F, NQ=F, RTY=F).
    All 8 calls run in parallel via ThreadPoolExecutor; results keep _MARKETS order.
    """
    spot_mode = _is_trading_hours()
    # Select spot or futures label+symbol for each row
    active = [
        (ls, ss) if spot_mode else (lf, sf)
        for ls, ss, lf, sf in _MARKETS
    ]
    order = {sym: i for i, (_, sym) in enumerate(active)}
    results: list[schemas.MarketItem] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        tasks = {
            pool.submit(_fetch_market_item, label, sym, not spot_mode): sym
            for label, sym in active
        }
        for task in as_completed(tasks):
            item = task.result()
            if item:
                results.append(item)
    results.sort(key=lambda x: order.get(x.ticker, 99))
    return results


# ── Ticker / company search (must be before /{ticker} to avoid shadowing) ─────

@router.get("/search", response_model=list[schemas.TickerSearchResult])
def search_stocks(q: str = Query(..., min_length=1)):
    """Autocomplete search for ticker symbols and company names via yfinance.
    Returns up to 8 results. Prefers longName over shortName for display.
    Returns [] on any error so the frontend autocomplete degrades gracefully.
    """
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
    """Convert a yfinance value to float, returning None for NaN / missing."""
    try:
        v = float(val)
        return None if pd.isna(v) else round(v, 4)
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> int | None:
    """Convert a yfinance value to int, returning None for zero or missing.
    Zero is treated as missing because yfinance returns 0 for unavailable integers.
    """
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

    # ETF / mutual-fund holdings — primary: ETFdb, fallback: yfinance top_holdings
    quote_type = info.get("quoteType", "")
    is_etf = quote_type in ("ETF", "MUTUALFUND")
    etf_holdings: list[schemas.ETFHolding] = []
    if is_etf:
        etf_holdings = _fetch_etfdb_holdings(ticker)
        if not etf_holdings:  # fallback
            try:
                holdings_df = t.funds_data.top_holdings
                if holdings_df is not None and not holdings_df.empty:
                    for sym, row in holdings_df.iterrows():
                        raw_weight = _safe_float(row.get("Holding Percent"))
                        weight = round(raw_weight * 100, 4) if raw_weight is not None else None
                        etf_holdings.append(schemas.ETFHolding(
                            symbol=str(sym) if sym else None,
                            name=str(row.get("Name", "")) or None,
                            weight=weight,
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
        is_etf=is_etf,
        etf_holdings=etf_holdings,
    )


# ── News endpoint ─────────────────────────────────────────────────────────────

def _parse_news(raw: list[dict]) -> list[schemas.NewsItem]:
    """Parse the nested yfinance news response format into flat NewsItem objects.
    yfinance wraps each article in a 'content' dict with nested 'provider',
    'canonicalUrl', and 'finance.stockTickers' fields. Related tickers are
    de-duped using a set comprehension before being stored as a list.
    Entries without a title are silently skipped.
    """
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
    """Return scored news articles for a ticker. Returns [] (not 404) when no
    news is available — ETFs and small-cap tickers often have sparse coverage.
    """
    ticker = ticker.upper().strip()
    t = yf.Ticker(ticker)
    raw = t.news or []
    return _parse_news(raw)


# ── Signals endpoint ──────────────────────────────────────────────────────────

@router.get("/{ticker}/signals", response_model=schemas.SignalsResponse)
def get_signals(ticker: str):
    """Compute composite Buy/Sell/Hold signal using 6 months of price history.
    Uses a separate history fetch (not the one from get_stock) so period and
    interval are always consistent regardless of the chart view the user is on.
    """
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
