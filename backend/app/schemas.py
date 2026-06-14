from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Any


# ── Portfolio ────────────────────────────────────────────────────────────────

class PortfolioCreate(BaseModel):
    ticker: str
    company_name: Optional[str] = None
    shares: float
    buy_price: float
    buy_date: Optional[str] = None  # auto-set to today if omitted
    notes: Optional[str] = None


class PortfolioUpdate(BaseModel):
    shares: Optional[float] = None
    buy_price: Optional[float] = None
    notes: Optional[str] = None


class PortfolioOut(BaseModel):
    id: int
    ticker: str
    company_name: Optional[str]
    shares: float
    buy_price: float
    buy_date: str
    notes: Optional[str]
    created_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ── Search history ────────────────────────────────────────────────────────────

class SearchHistoryOut(BaseModel):
    id: int
    ticker: str
    company_name: Optional[str] = None
    searched_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ── Stocks (yfinance) ─────────────────────────────────────────────────────────

class OHLCVPoint(BaseModel):
    date: int   # Unix timestamp in seconds (supports daily + intraday)
    open: float
    high: float
    low: float
    close: float
    volume: int


class FibonacciLevels(BaseModel):
    high_60d: float
    low_60d: float
    levels: dict[str, float]


class InstitutionalHolder(BaseModel):
    holder: str
    shares: Optional[int] = None
    value: Optional[float] = None
    pct_out: Optional[float] = None
    date_reported: Optional[str] = None


class ETFHolding(BaseModel):
    symbol: Optional[str] = None
    name: Optional[str] = None
    weight: Optional[float] = None  # percentage weight (e.g. 7.12 means 7.12%)


class ChartDataResponse(BaseModel):
    """Lightweight response for history expansion — chart data only, no company info."""
    ohlcv: list[OHLCVPoint]
    sma_50: list[Optional[float]]
    sma_200: list[Optional[float]]
    ema_50: list[Optional[float]]
    ema_100: list[Optional[float]]
    ema_150: list[Optional[float]]
    ema_200: list[Optional[float]]
    fibonacci: FibonacciLevels
    trend_lines: Optional[dict] = None


class StockResponse(BaseModel):
    ticker: str
    company_name: str
    current_price: Optional[float]
    previous_close: Optional[float]
    day_high: Optional[float]
    day_low: Optional[float]
    day_volume: Optional[int]
    avg_volume: Optional[int]
    market_cap: Optional[int]
    week_52_high: Optional[float]
    week_52_low: Optional[float]
    # Extended-hours prices (None during regular market hours)
    post_market_price: Optional[float] = None
    post_market_change: Optional[float] = None
    post_market_change_pct: Optional[float] = None
    pre_market_price: Optional[float] = None
    pre_market_change: Optional[float] = None
    pre_market_change_pct: Optional[float] = None
    ohlcv: list[OHLCVPoint]
    sma_50: list[Optional[float]]
    sma_200: list[Optional[float]]
    ema_50: list[Optional[float]]
    ema_100: list[Optional[float]]
    ema_150: list[Optional[float]]
    ema_200: list[Optional[float]]
    fibonacci: FibonacciLevels
    institutional_holders: list[InstitutionalHolder]
    is_etf: bool = False
    etf_holdings: list[ETFHolding] = []
    trend_lines: Optional[dict] = None


# ── News & Signals ────────────────────────────────────────────────────────────

class TickerSearchResult(BaseModel):
    ticker: str
    name: str


class NewsItem(BaseModel):
    title: str
    publisher: str
    url: str
    published_at: str      # ISO-8601 string for chart sync
    sentiment: str         # 'good' | 'bad' | 'neutral'
    compound_score: float
    related_tickers: list[str] = []


class SignalsResponse(BaseModel):
    ticker: str
    buy: float
    sell: float
    hold: float
    breakdown: dict[str, Any]


# ── Portfolio positions (with live P&L) ──────────────────────────────────────

class PositionOut(BaseModel):
    id: int
    ticker: str
    company_name: Optional[str]
    shares: float
    buy_price: float
    buy_date: str
    notes: Optional[str]
    current_price: Optional[float] = None
    market_value: Optional[float] = None
    pnl_dollar: Optional[float] = None
    pnl_pct: Optional[float] = None

    model_config = {"from_attributes": True}


# ── Market ticker bar ────────────────────────────────────────────────────────

class MarketItem(BaseModel):
    label: str         # display name, e.g. "S&P 500" or "S&P Fut."
    ticker: str        # yfinance symbol, e.g. "^GSPC" or "ES=F"
    price: float
    change: float      # absolute change from previous close
    change_pct: float  # percentage change
    is_futures: bool = False  # True outside 7 AM–8 PM ET Mon–Fri → futures mode


# ── Watchlist ─────────────────────────────────────────────────────────────────

class WatchlistCreate(BaseModel):
    name: str

class WatchlistUpdate(BaseModel):
    name: str

class WatchlistOut(BaseModel):
    id: int
    name: str
    item_count: int
    created_at: Optional[datetime]
    model_config = {"from_attributes": True}

class WatchlistItemAdd(BaseModel):
    tickers: str          # comma-separated, e.g. "AAPL, MSFT, NVDA"
    notes: Optional[str] = None

class WatchlistReorder(BaseModel):
    ids: list[int]        # item IDs in the desired order

class WatchlistItemOut(BaseModel):
    id: int
    watchlist_id: int
    ticker: str
    company_name: Optional[str]
    notes: Optional[str]
    added_at: Optional[datetime]
    current_price: Optional[float] = None
    previous_close: Optional[float] = None
    day_change: Optional[float] = None
    day_change_pct: Optional[float] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    market_cap: Optional[int] = None
    avg_volume: Optional[int] = None
    post_market_price: Optional[float] = None
    post_market_change: Optional[float] = None
    post_market_change_pct: Optional[float] = None
    pre_market_price: Optional[float] = None
    pre_market_change: Optional[float] = None
    pre_market_change_pct: Optional[float] = None
    model_config = {"from_attributes": True}


class PriceResponse(BaseModel):
    """Lightweight price snapshot — fast_info only, no OHLCV or company info."""
    current_price: Optional[float] = None
    previous_close: Optional[float] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None


# ── Recommendations ──────────────────────────────────────────────────────────

class RecommendationItem(BaseModel):
    ticker: str
    company_name: Optional[str] = None
    current_price: Optional[float] = None
    day_change: Optional[float] = None
    day_change_pct: Optional[float] = None
    buy_pct: float
    sell_pct: float
    hold_pct: float
    breakdown: dict[str, Any] = {}   # sma_cross, ema_cross, price_vs_sma50, volume, news_good/bad/neutral
    top_news: list[NewsItem] = []
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    risk_reward: Optional[float] = None
    fibonacci_levels: Optional[dict] = None


# ── Read stocks ───────────────────────────────────────────────────────────────

class ReadStockOut(BaseModel):
    id: int
    ticker: str
    marked_read_at: Optional[datetime]

    model_config = {"from_attributes": True}
