import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, engine as eng
from app.routes.stocks import _parse_news, _safe_float

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


def _last_val(arr: list) -> float | None:
    for v in reversed(arr):
        if v is not None:
            return v
    return None


def _analyze(ticker: str, require_buy: bool = True) -> schemas.RecommendationItem | None:
    """Run the full signal + Fibonacci analysis for one ticker.

    When require_buy=False, returns the item even if buy_pct < 50 (used by the
    single-ticker search endpoint so the user can see any stock's analysis).
    """
    try:
        t    = yf.Ticker(ticker)
        hist = t.history(period="6mo", interval="1d")
        if hist.empty or len(hist) < 20:
            return None

        closes  = hist["Close"].tolist()
        volumes = hist["Volume"].tolist()

        fi   = t.fast_info
        last = _safe_float(fi.last_price)
        prev = _safe_float(fi.previous_close)
        if not last:
            return None

        sma_50  = eng.calculate_sma(closes, 50)
        sma_200 = eng.calculate_sma(closes, 200)
        ema_50  = eng.calculate_ema(closes, 50)
        ema_100 = eng.calculate_ema(closes, 100)

        news_items = _parse_news(t.news or [])[:5]
        sentiments = [n.sentiment for n in news_items]

        result = eng.calculate_signals(
            last,
            _last_val(sma_50),
            _last_val(sma_200),
            _last_val(ema_50),
            _last_val(ema_100),
            sentiments,
            closes,
            volumes,
        )

        if require_buy and result["buy"] < 50:
            return None

        try:
            h60, l60   = eng.get_60day_high_low(hist)
            fib_raw    = eng.calculate_fibonacci(h60, l60)
            fib_sorted = sorted(fib_raw.values())
        except Exception:
            fib_raw    = {}
            fib_sorted = []

        entry     = next((p for p in reversed(fib_sorted) if p <= last), last)
        stop_loss = next((p for p in reversed(fib_sorted) if p < entry - 0.005), None)
        above     = [p for p in fib_sorted if p > entry + 0.005]
        target_1  = above[0] if above else None
        target_2  = above[1] if len(above) > 1 else None

        rr = None
        if target_1 and stop_loss and (entry - stop_loss) > 0:
            rr = round((target_1 - entry) / (entry - stop_loss), 1)

        info         = t.info
        company_name = info.get("longName") or info.get("shortName") or None
        chg          = round(last - prev, 4) if prev else None
        chg_pct      = round(chg / prev * 100, 2) if chg and prev else None

        return schemas.RecommendationItem(
            ticker         = ticker,
            company_name   = company_name,
            current_price  = round(last, 4),
            day_change     = chg,
            day_change_pct = chg_pct,
            buy_pct        = result["buy"],
            sell_pct       = result["sell"],
            hold_pct       = result["hold"],
            breakdown      = result["breakdown"],
            top_news       = news_items[:3],
            entry_price    = round(entry, 4),
            stop_loss      = round(stop_loss, 4) if stop_loss else None,
            target_1       = round(target_1, 4) if target_1 else None,
            target_2       = round(target_2, 4) if target_2 else None,
            risk_reward    = rr,
            fibonacci_levels = fib_raw or None,
        )
    except Exception:
        return None


@router.get("/", response_model=list[schemas.RecommendationItem])
def get_recommendations(db: Session = Depends(get_db)):
    """Return up to 10 buy-signal stocks from the user's portfolio and watchlists."""
    portfolio_tickers = {r[0] for r in db.query(models.Portfolio.ticker).all()}
    watchlist_tickers = {r[0] for r in db.query(models.WatchlistItem.ticker).all()}
    all_tickers = list(portfolio_tickers | watchlist_tickers)

    if not all_tickers:
        return []

    results: list[schemas.RecommendationItem] = []
    with ThreadPoolExecutor(max_workers=min(len(all_tickers), 8)) as pool:
        futures = {pool.submit(_analyze, tkr, True): tkr for tkr in all_tickers}
        for future in as_completed(futures):
            item = future.result()
            if item:
                results.append(item)

    results.sort(key=lambda x: x.buy_pct, reverse=True)
    return results[:10]


_INDEX_MAP = {
    "SPY": "S&P 500",
    "QQQ": "NASDAQ 100",
    "DIA": "Dow Jones",
}

_FUTURES_MAP = {
    "ES=F": "S&P Futures",
    "NQ=F": "NASDAQ Futures",
    "YM=F": "Dow Futures",
}


@router.get("/market-pulse")
def get_market_pulse():
    """Signal analysis for SPY/QQQ/DIA + live futures prices for ES=F/NQ=F/YM=F.

    Returns direction (bullish/bearish/neutral) derived from buy_pct vs sell_pct,
    plus current futures change so the user can see pre/post-market sentiment.
    Must stay above /{ticker} route so FastAPI doesn't eat 'market-pulse' as a ticker.
    """

    def _fetch_index(ticker: str) -> dict | None:
        item = _analyze(ticker, require_buy=False)
        if not item:
            return None
        if item.buy_pct >= 55:
            direction = "bullish"
        elif item.sell_pct >= 55:
            direction = "bearish"
        else:
            direction = "neutral"
        return {
            "ticker":    ticker,
            "label":     _INDEX_MAP[ticker],
            "price":     item.current_price,
            "chg_pct":   item.day_change_pct,
            "buy_pct":   item.buy_pct,
            "sell_pct":  item.sell_pct,
            "direction": direction,
            "breakdown": item.breakdown,
        }

    def _fetch_future(ticker: str) -> dict | None:
        try:
            fi    = yf.Ticker(ticker).fast_info
            price = _safe_float(fi.last_price)
            prev  = _safe_float(fi.previous_close)
            chg_pct = round((price - prev) / prev * 100, 2) if price and prev else None
            return {"ticker": ticker, "label": _FUTURES_MAP[ticker], "price": price, "chg_pct": chg_pct}
        except Exception:
            return None

    index_keys   = list(_INDEX_MAP)
    futures_keys = list(_FUTURES_MAP)
    idx_results: list[tuple[int, dict]] = []
    fut_results: list[tuple[int, dict]] = []

    with ThreadPoolExecutor(max_workers=6) as pool:
        fmap = {}
        for t in index_keys:
            fmap[pool.submit(_fetch_index, t)] = ("index", index_keys.index(t))
        for t in futures_keys:
            fmap[pool.submit(_fetch_future, t)] = ("future", futures_keys.index(t))

        for f in as_completed(fmap):
            kind, pos = fmap[f]
            data = f.result()
            if kind == "index" and data:
                idx_results.append((pos, data))
            elif kind == "future" and data:
                fut_results.append((pos, data))

    idx_results.sort(key=lambda x: x[0])
    fut_results.sort(key=lambda x: x[0])

    return {
        "indices": [d for _, d in idx_results],
        "futures": [d for _, d in fut_results],
    }


@router.get("/{ticker}", response_model=schemas.RecommendationItem)
def get_recommendation(ticker: str):
    """Analyse a single ticker and return its full signal + Fibonacci breakdown.

    Unlike the bulk endpoint, this always returns a result (even if buy_pct < 50)
    so the user can inspect any stock on demand.
    """
    item = _analyze(ticker.upper(), require_buy=False)
    if not item:
        raise HTTPException(status_code=404, detail=f"Could not fetch data for {ticker.upper()}")
    return item
