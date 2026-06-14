import re
import html as html_lib
import logging
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
logger = logging.getLogger(__name__)

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
        results = yf.Search(q.upper(), max_results=20)
        quotes = results.quotes or []
        # Only return equities, ETFs, and mutual funds.
        # Exclude forex pairs (=X), futures (=F), indices (^), and crypto pairs.
        allowed = {"equity", "etf", "mutualfund"}
        filtered = [
            r for r in quotes
            if r.get("symbol")
            and not r["symbol"].endswith("=X")
            and not r["symbol"].endswith("=F")
            and not r["symbol"].startswith("^")
            and r.get("quoteType", "").lower() in allowed
        ]
        return [
            schemas.TickerSearchResult(
                ticker=r["symbol"],
                name=r.get("longname") or r.get("shortname") or r["symbol"],
            )
            for r in filtered[:8]
        ]
    except Exception:
        return []


@router.get("/bulk", response_model=list[schemas.WatchlistItemOut])
def get_bulk_prices(tickers: str = Query(..., description="Comma-separated ticker symbols")):
    """Live price snapshot for multiple tickers without needing a watchlist in the DB.
    Used by the ETF holdings preview popup. Same data shape as watchlist items.
    Must be registered before /{ticker} so '/bulk' isn't captured as a ticker symbol.
    """
    ticker_list = [t.strip().upper() for t in tickers.split(',') if t.strip()][:100]
    if not ticker_list:
        return []

    def _fetch(tkr: str) -> tuple[str, dict]:
        try:
            t     = yf.Ticker(tkr)
            fi    = t.fast_info
            info  = t.info
            last  = float(fi.last_price)
            prev  = float(fi.previous_close)
            last  = last if last == last else None
            prev  = prev if prev == prev else None
            chg   = round(last - prev, 4) if last is not None and prev else None
            chg_p = round(chg / prev * 100, 2) if chg is not None and prev else None
            reg   = round(last, 4) if last else None
            post_p = _safe_float(info.get("postMarketPrice"))
            post_c = _safe_float(info.get("postMarketChange"))
            pre_p  = _safe_float(info.get("preMarketPrice"))
            pre_c  = _safe_float(info.get("preMarketChange"))
            return tkr, {
                "company_name":           info.get("longName") or info.get("shortName") or None,
                "current_price":          reg,
                "previous_close":         round(prev, 4) if prev else None,
                "day_change":             chg,
                "day_change_pct":         chg_p,
                "day_high":               _safe_float(fi.day_high),
                "day_low":                _safe_float(fi.day_low),
                "week_52_high":           _safe_float(fi.year_high),
                "week_52_low":            _safe_float(fi.year_low),
                "market_cap":             _safe_int(fi.market_cap),
                "avg_volume":             _safe_int(fi.three_month_average_volume),
                "post_market_price":      post_p,
                "post_market_change":     post_c,
                "post_market_change_pct": round(post_c / reg * 100, 2) if post_c and reg else None,
                "pre_market_price":       pre_p,
                "pre_market_change":      pre_c,
                "pre_market_change_pct":  round(pre_c / reg * 100, 2) if pre_c and reg else None,
            }
        except Exception:
            return tkr, {}

    prices: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(len(ticker_list), 12)) as pool:
        futures = {pool.submit(_fetch, tkr): tkr for tkr in ticker_list}
        for future in as_completed(futures):
            tkr, data = future.result()
            prices[tkr] = data

    return [
        schemas.WatchlistItemOut(
            id=0, watchlist_id=0,
            ticker=tkr,
            notes=None, added_at=None,
            **prices.get(tkr, {}),
        )
        for tkr in ticker_list
        if tkr in prices
    ]


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
    sma_50  = eng.calculate_sma(closes, 50)
    sma_200 = eng.calculate_sma(closes, 200)
    ema_50  = eng.calculate_ema(closes, 50)
    ema_100 = eng.calculate_ema(closes, 100)
    ema_150 = eng.calculate_ema(closes, 150)
    ema_200 = eng.calculate_ema(closes, 200)

    # Fibonacci (60-day high/low)
    high_60, low_60 = eng.get_60day_high_low(hist)
    fib_levels = eng.calculate_fibonacci(high_60, low_60)

    # Trend lines (pivot-based support / resistance)
    trend_lines = eng.calculate_trend_lines(hist)

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

    # Extended-hours prices — derive pct from the change/price so the unit is
    # always consistent (percentage like 1.28 for 1.28%) regardless of yfinance version.
    reg_price   = _safe_float(fast.last_price)
    post_price  = _safe_float(info.get("postMarketPrice"))
    post_change = _safe_float(info.get("postMarketChange"))
    post_pct    = round(post_change / reg_price * 100, 2) if post_change and reg_price else None
    pre_price   = _safe_float(info.get("preMarketPrice"))
    pre_change  = _safe_float(info.get("preMarketChange"))
    pre_pct     = round(pre_change / reg_price * 100, 2) if pre_change and reg_price else None

    return schemas.StockResponse(
        ticker=ticker,
        company_name=info.get("longName") or info.get("shortName") or ticker,
        current_price=reg_price,
        previous_close=_safe_float(info.get("previousClose")),
        day_high=_safe_float(fast.day_high),
        day_low=_safe_float(fast.day_low),
        day_volume=_safe_int(hist["Volume"].iloc[-1]),
        avg_volume=_safe_int(fast.three_month_average_volume),
        market_cap=_safe_int(fast.market_cap),
        week_52_high=_safe_float(fast.year_high),
        week_52_low=_safe_float(fast.year_low),
        post_market_price=post_price,
        post_market_change=post_change,
        post_market_change_pct=post_pct,
        pre_market_price=pre_price,
        pre_market_change=pre_change,
        pre_market_change_pct=pre_pct,
        ohlcv=ohlcv,
        sma_50=sma_50,
        sma_200=sma_200,
        ema_50=ema_50,
        ema_100=ema_100,
        ema_150=ema_150,
        ema_200=ema_200,
        fibonacci=schemas.FibonacciLevels(
            high_60d=round(high_60, 4),
            low_60d=round(low_60, 4),
            levels=fib_levels,
        ),
        institutional_holders=holders,
        is_etf=is_etf,
        etf_holdings=etf_holdings,
        trend_lines=trend_lines,
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


@router.get("/{ticker}/ohlcv", response_model=schemas.ChartDataResponse)
def get_chart_data(ticker: str, period: str = "1y", interval: str = "1d"):
    """Lightweight endpoint for chart history expansion (infinite scroll).
    Returns only OHLCV + indicators — skips the expensive company-info, holders,
    and ETF calls so the response is fast enough to feel seamless while panning.
    """
    ticker = ticker.upper()
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=period, interval=interval)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if hist.empty:
        raise HTTPException(status_code=404, detail=f"No OHLCV data for {ticker}")

    ohlcv = eng.extract_ohlcv(hist)
    closes = [c["close"] for c in ohlcv]
    high_60, low_60 = eng.get_60day_high_low(hist)

    return schemas.ChartDataResponse(
        ohlcv=ohlcv,
        sma_50=eng.calculate_sma(closes, 50),
        sma_200=eng.calculate_sma(closes, 200),
        ema_50=eng.calculate_ema(closes, 50),
        ema_100=eng.calculate_ema(closes, 100),
        ema_150=eng.calculate_ema(closes, 150),
        ema_200=eng.calculate_ema(closes, 200),
        fibonacci=schemas.FibonacciLevels(
            high_60d=round(high_60, 4),
            low_60d=round(low_60, 4),
            levels=eng.calculate_fibonacci(high_60, low_60),
        ),
        trend_lines=eng.calculate_trend_lines(hist),
    )


@router.get("/{ticker}/price", response_model=schemas.PriceResponse)
def get_price(ticker: str):
    """Lightweight price snapshot using fast_info only — no OHLCV, no company info.
    Used by the Dashboard auto-refresh timer so the chart stays visible without
    re-downloading all historical data.
    """
    ticker = ticker.upper().strip()
    try:
        fast = yf.Ticker(ticker).fast_info
        return schemas.PriceResponse(
            current_price=_safe_float(fast.last_price),
            previous_close=_safe_float(fast.previous_close),
            day_high=_safe_float(fast.day_high),
            day_low=_safe_float(fast.day_low),
        )
    except Exception:
        raise HTTPException(status_code=404, detail=f"Price unavailable for '{ticker}'")


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

    sma_50  = eng.calculate_sma(closes, 50)
    sma_200 = eng.calculate_sma(closes, 200)
    ema_50  = eng.calculate_ema(closes, 50)
    ema_100 = eng.calculate_ema(closes, 100)

    news_items = _parse_news(t.news or [])
    sentiments = [n.sentiment for n in news_items]

    result = eng.calculate_signals(
        current_price=closes[-1],
        sma_20_last=sma_50[-1],    # signals engine uses this slot for fast MA
        sma_50_last=sma_200[-1],
        ema_20_last=ema_50[-1],
        ema_50_last=ema_100[-1],
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


# ── Company events endpoint ───────────────────────────────────────────────────

@router.get("/{ticker}/events")
def get_stock_events(ticker: str):
    """Return upcoming company events: next earnings date (with EPS/revenue estimates)
    and ex-dividend date.  Uses t.calendar as primary source, falls back to
    t.get_earnings_dates() when calendar has no earnings entry.
    Always returns a list (empty if nothing found) — never raises 404.
    """
    import math
    ticker = ticker.upper().strip()
    t = yf.Ticker(ticker)
    events: list[dict] = []
    today = datetime.now().date()

    def _safe_ts(val):
        """Pandas / datetime Timestamp → date, None on failure."""
        if val is None:
            return None
        try:
            if hasattr(val, 'date'):
                return val.date()
            if hasattr(val, 'to_pydatetime'):
                return val.to_pydatetime().date()
        except Exception:
            pass
        return None

    def _safe_num(val):
        try:
            f = float(val)
            return None if math.isnan(f) else f
        except (TypeError, ValueError):
            return None

    def _days_label(n: int) -> str:
        if n == 0:   return "Today"
        if n == 1:   return "Tomorrow"
        if n == -1:  return "Yesterday"
        if n > 0:    return f"in {n} days"
        return f"{abs(n)} days ago"

    try:
        cal = t.calendar or {}
        if isinstance(cal, dict):
            # ── Earnings ──────────────────────────────────────────────────────
            earn_dates = cal.get("Earnings Date") or []
            if earn_dates:
                d1 = _safe_ts(earn_dates[0])
                d2 = _safe_ts(earn_dates[-1]) if len(earn_dates) > 1 else None
                if d1:
                    eps     = _safe_num(cal.get("Earnings Average"))
                    eps_lo  = _safe_num(cal.get("Earnings Low"))
                    eps_hi  = _safe_num(cal.get("Earnings High"))
                    rev     = _safe_num(cal.get("Revenue Average"))
                    diff    = (d1 - today).days
                    events.append({
                        "type":             "earnings",
                        "label":            "Earnings",
                        "date":             d1.strftime("%b %d, %Y"),
                        "date_end":         d2.strftime("%b %d, %Y") if d2 and d2 != d1 else None,
                        "days_until":       diff,
                        "days_label":       _days_label(diff),
                        "eps_estimate":     round(eps,    2) if eps    is not None else None,
                        "eps_low":          round(eps_lo, 2) if eps_lo is not None else None,
                        "eps_high":         round(eps_hi, 2) if eps_hi is not None else None,
                        "revenue_estimate": int(rev)         if rev    is not None else None,
                    })

            # ── Ex-Dividend ───────────────────────────────────────────────────
            ex_div = _safe_ts(cal.get("Ex-Dividend Date"))
            if ex_div:
                diff = (ex_div - today).days
                events.append({
                    "type":             "dividend",
                    "label":            "Ex-Dividend",
                    "date":             ex_div.strftime("%b %d, %Y"),
                    "date_end":         None,
                    "days_until":       diff,
                    "days_label":       _days_label(diff),
                    "eps_estimate":     None,
                    "eps_low":          None,
                    "eps_high":         None,
                    "revenue_estimate": None,
                })
    except Exception as e:
        logger.warning("calendar fetch failed for %s: %s", ticker, e)

    # Fallback: use earnings_dates DataFrame when calendar had no earnings entry
    if not any(e["type"] == "earnings" for e in events):
        try:
            edf = t.get_earnings_dates(limit=8)
            if edf is not None and not edf.empty:
                rep_col = "Reported EPS" if "Reported EPS" in edf.columns else None
                future_df = edf[edf[rep_col].isna()] if rep_col else edf[edf.index >= pd.Timestamp.now(tz="UTC")]
                if not future_df.empty:
                    idx = future_df.index[0]
                    d   = _safe_ts(idx) or idx.to_pydatetime().date()
                    eps_col = "EPS Estimate" if "EPS Estimate" in future_df.columns else None
                    eps_val = _safe_num(future_df.iloc[0][eps_col]) if eps_col else None
                    diff    = (d - today).days
                    events.append({
                        "type":             "earnings",
                        "label":            "Earnings",
                        "date":             d.strftime("%b %d, %Y"),
                        "date_end":         None,
                        "days_until":       diff,
                        "days_label":       _days_label(diff),
                        "eps_estimate":     round(eps_val, 2) if eps_val is not None else None,
                        "eps_low":          None,
                        "eps_high":         None,
                        "revenue_estimate": None,
                    })
        except Exception as e:
            logger.warning("earnings_dates fallback failed for %s: %s", ticker, e)

    return events
