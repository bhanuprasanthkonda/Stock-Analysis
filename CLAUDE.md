# CLAUDE.md — Local Stock Analyzer & Portfolio Tracker

This file is read automatically by Claude Code. It contains everything needed to understand, maintain, and extend this project.

---

## What This Project Is

A local-first stock analysis + portfolio tracker. No cloud, no Docker, no auth, no subscriptions. Runs entirely on the user's machine. Data comes from Yahoo Finance via `yfinance`.

---

## Strict Rules — Never Break These

1. **No Tailwind CSS** — never install it, never use it
2. **No custom CSS** — no `.css`/`.scss` files, no `<style>` blocks inside `.vue` files
3. **Vuetify-only layouts** — all spacing, color, grid, and alignment via Vuetify props and utility classes (`v-row`, `v-col`, `pa-4`, `text-success`, `text-medium-emphasis`, etc.)
4. **Vue 3 Composition API only** — always `<script setup>`, never Options API
5. **No Docker, no auth, no cloud** — keep it local and simple
6. **Keep `Project_specs/features.md` in sync** — whenever a feature is added or updated in the code, update `Project_specs/features.md` to reflect the change before considering the task complete

---

## How to Run

```bash
# Terminal 1 — backend
cd backend && source venv/bin/activate && uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend && npm run dev
```

Or double-click `start.sh` (macOS/Linux) / `start.bat` (Windows).

---

## Architecture

```
stock_analysis/
├── CLAUDE.md
├── start.sh / start.bat
├── Project_specs/
│   ├── Spec.md          — technical spec (schema, endpoints, data types)
│   ├── features.md      — full feature documentation
│   └── BuildGuide.md    — step-by-step rebuild instructions
├── backend/
│   ├── venv/
│   ├── requirements.txt
│   ├── stocks.db        — SQLite (auto-created, gitignored)
│   └── app/
│       ├── main.py      — FastAPI app + CORS + lifespan
│       ├── database.py  — SQLAlchemy engine + init_db (runs migrations too)
│       ├── models.py    — Portfolio, SearchHistory, ReadStock ORM models
│       ├── schemas.py   — Pydantic request/response schemas
│       ├── engine.py    — SMA, EMA, Fibonacci, OHLCV extract, VADER sentiment, signals
│       └── routes/
│           ├── stocks.py    — GET /stocks/{ticker}?period&interval, /news, /signals
│           └── portfolio.py — CRUD /portfolio/, /positions (live P&L), /history
└── frontend/
    └── src/
        ├── main.js          — createApp + vuetify + vue-router
        ├── App.vue          — nav drawer + app bar + router-view
        ├── api.js           — axios instance (baseURL: http://localhost:8000)
        ├── plugins/vuetify.js
        ├── components/
        │   ├── StockChart.vue   — lightweight-charts chart (candlestick + overlays)
        │   ├── NewsCard.vue     — single news item with sentiment chip
        │   └── Signals.vue     — buy/sell/hold percentage display
        └── views/
            ├── Dashboard.vue   — main search + info panel + chart
            ├── Portfolio.vue   — positions table with live P&L
            └── History.vue     — search history table
```

---

## Key Technical Decisions

### OHLCV dates are Unix timestamps (int)
`OHLCVPoint.date` is `int` seconds since epoch — NOT a date string. This lets lightweight-charts handle both daily and intraday data with the same code. News markers use `tsToUTCDate(unix)` to match by calendar date.

### lightweight-charts v4 (not ApexCharts)
Charting uses TradingView's `lightweight-charts` library. Key patterns:
```js
import { createChart, ColorType, CrosshairMode, LineStyle } from 'lightweight-charts'

chart = createChart(el, { ... })
candleS = chart.addCandlestickSeries({ ... })
volS = chart.addHistogramSeries({ priceScaleId: '' })   // hidden overlay scale
chart.priceScale('').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } })
candleS.createPriceLine({ price, color, lineStyle: LineStyle.Dashed })  // Fibonacci
candleS.setMarkers([{ time, position, color, shape }])  // news markers
```

### Period/interval are props, not local state
`StockChart.vue` receives `period` and `interval` as props from `Dashboard.vue`. It emits `fetch-data` events up. This prevents the highlight from resetting on remount when `stock.value = null` during a period change.

### Search history is deduplicated server-side
Each search deletes the old `SearchHistory` row for that ticker and inserts a fresh one. This keeps history unique-per-ticker and always sorted newest-first without any dedup logic on the frontend.

### `buy_date` is auto-set server-side
Portfolio positions don't ask the user for a buy date — it's auto-filled with today's date in the `add_position` route. The `PortfolioCreate` schema accepts `buy_date: Optional[str] = None`.

### Database migrations without Alembic
New columns are added at startup in `database.py` using SQLite `PRAGMA table_info` + `ALTER TABLE ADD COLUMN`. This avoids Alembic complexity for a local single-user tool.

---

## yfinance Attribute Reference

Use these — the old names will throw `AttributeError`:
```python
fast = t.fast_info
fast.last_price          # current price
fast.year_high           # 52-week high (NOT fifty_two_week_high)
fast.year_low            # 52-week low  (NOT fifty_two_week_low)
fast.day_high
fast.day_low
fast.market_cap
fast.three_month_average_volume
```

Valid `period` strings: `1d` `5d` `1mo` `3mo` `6mo` `ytd` `1y` `2y` `5y` `max`  
Valid `interval` strings: `1m` `2m` `5m` `15m` `30m` `60m` `1h` `1d` `5d` `1wk` `1mo` `3mo`

---

## Vuetify Chip Toggle Pattern

ON = solid fill in the line's hex color. OFF = text-only in grey. Example:
```html
<v-chip
  size="small"
  :color="showSMA20 ? '#2196F3' : 'grey'"
  :variant="showSMA20 ? 'flat' : 'text'"
  @click="showSMA20 = !showSMA20"
>SMA 20</v-chip>
```

---

## Chart Line Colors (match these exactly in both chart + chips)

| Indicator | Hex |
|-----------|-----|
| SMA 50 | `#FF9800` |
| SMA 200 | `#26C6DA` |
| EMA 50 | `#E91E63` |
| EMA 100 | `#FF7043` |
| EMA 150 | `#66BB6A` |
| EMA 200 | `#9C27B0` |
| Vol | `#546E7A` |
| Fib | `#FFA726` |
| News | `#4CAF50` |
| ↑ Trend | `#26A69A` |
| ↓ Trend | `#EF5350` |

---

## Routes

| Route | View | Notes |
|-------|------|-------|
| `/dashboard` | Dashboard.vue | accepts `?ticker=` query param to auto-search |
| `/recommendations` | Recommendations.vue | buy-signal cards from portfolio + watchlist tickers |
| `/portfolio` | Portfolio.vue | clicking a ticker navigates to `/dashboard?ticker=X` |
| `/watchlist` | Watchlist.vue | two-panel: list selector left, items table right |
| `/history` | History.vue | same click behaviour |

---

## Common Tasks

**Add a new backend field:**
1. Add column to model in `models.py`
2. Add migration in `database.py` `init_db()` (PRAGMA + ALTER TABLE)
3. Add field to schema in `schemas.py`
4. Populate it in the relevant route

**Add a new chart overlay:**
1. Add `showXxx = ref(false)` toggle
2. Add the series in `initChart()` with the chosen color
3. Add `watch(showXxx, ...)` to toggle data
4. Add a `v-chip` in the template with matching color
5. Add color to `CLAUDE.md` chart colors table

---

## Function Reference

Every significant function across the codebase has a JSDoc / docstring comment in the source. This section serves as a quick index.

### `backend/app/engine.py`
| Function | Purpose |
|----------|---------|
| `calculate_sma(closes, period)` | SMA with leading `None`s to match input length |
| `calculate_ema(closes, period)` | EMA seeded with SMA to avoid cold-start spikes |
| `calculate_fibonacci(high, low)` | 7 standard retracement levels as `{"23.6": price, ...}` |
| `calculate_trend_lines(df, window=10)` | Pivot-based uptrend support + downtrend resistance lines, each extended to last candle |
| `extract_ohlcv(df)` | DataFrame → list of `{date(unix), open, high, low, close, volume}` |
| `get_60day_high_low(df)` | (high, low) over last 60 candles — Fibonacci reference range |
| `score_headline(text)` | VADER sentiment → `(label, compound)` where label ∈ good/bad/neutral |
| `calculate_signals(...)` | Composite Buy/Sell/Hold: tech 50% + sentiment 35% + volume 15% |

### `backend/app/database.py`
| Function | Purpose |
|----------|---------|
| `init_db()` | Create tables + PRAGMA-based column migrations — called from FastAPI lifespan |
| `get_db()` | FastAPI dependency: yields SQLAlchemy session, guaranteed close in `finally` |

### `backend/app/routes/stocks.py`
| Function | Purpose |
|----------|---------|
| `_fetch_etfdb_holdings(ticker)` | ETFdb.com holdings via 2-step: page scrape for `by_etf` ID, then paginated data_set API |
| `_safe_float(val)` | yfinance value → float, `None` for NaN |
| `_safe_int(val)` | yfinance value → int, `None` for zero (yfinance returns 0 for missing ints) |
| `search_stocks(q)` | Autocomplete via `yf.Search`; returns `[]` on error |
| `get_stock(ticker, ...)` | Main stock endpoint: OHLCV + indicators + ETF holdings + institutional holders |
| `_parse_news(raw)` | Flattens yfinance nested news format into `NewsItem` list |
| `get_news(ticker)` | Returns `[]` (not 404) when no news — ETFs often have sparse coverage |
| `get_signals(ticker)` | Composite signal using 6mo history, independent of chart period |
| `get_stock_events(ticker)` | Next earnings date + EPS/revenue estimates + ex-dividend date; uses `t.calendar` with `get_earnings_dates()` fallback; always returns list, never 404 |

### `backend/app/routes/portfolio.py`
| Function | Purpose |
|----------|---------|
| `list_portfolio()` | All positions, newest first |
| `add_position(payload)` | Add position; auto-sets `buy_date` to today |
| `update_position(id, payload)` | Partial update (shares, buy_price, notes only) |
| `delete_position(id)` | Delete by ID |
| `list_history()` | 20 most recent unique tickers from search history |
| `mark_read(ticker)` | Remove from history + log to read_stocks table |
| `list_positions()` | Positions with live P&L; fetches price once per unique ticker |

### `backend/app/routes/watchlist.py`
| Function | Purpose |
|----------|---------|
| `list_watchlists()` | All watchlists with `item_count` each |
| `create_watchlist(payload)` | Create a named watchlist |
| `delete_watchlist(wl_id)` | Delete watchlist + all items (manual cascade for SQLite) |
| `list_items(wl_id)` | Items for a watchlist with live price + day change; batches yfinance calls |
| `add_items(wl_id, payload)` | Parse comma-separated tickers, skip duplicates, auto-fill company_name, return updated items |
| `remove_item(wl_id, item_id)` | Remove a single ticker from a watchlist |

### `frontend/src/components/StockChart.vue`
| Function | Purpose |
|----------|---------|
| `onPeriodSelect(p)` | Emits `fetch-data` with the default interval for the chosen period |
| `onIntervalSelect(i)` | Emits `fetch-data` keeping current period, only candle size changes |
| `buildCandles()` | OHLCV → lightweight-charts candlestick shape |
| `buildLine(arr)` | SMA/EMA array (with leading nulls) → `{time, value}` pairs |
| `buildVolumes()` | Volume bars with green/red tinting based on candle direction |
| `applyFib()` | Clear + redraw Fibonacci price lines on the candlestick series |
| `tsToUTCDate(unix)` | Unix seconds → `"YYYY-MM-DD"` in UTC for news marker matching |
| `applyNewsMarkers()` | One marker per day (highest magnitude article); sorted ascending for lightweight-charts |
| `initChart()` | Create chart + all series + ResizeObserver |
| `refreshAll()` | Push fresh data into every series + fit time scale |

### `frontend/src/views/Dashboard.vue`
| Function | Purpose |
|----------|---------|
| `fetchHistory()` | Load search history chips; non-critical, failure silently ignored |
| `fetchMyPosition(ticker)` | Find current ticker in positions list for the "My Position" card |
| `onSearchType(text)` | Debounced autocomplete (300ms) |
| `searchStock(sym)` | Fire stock + news + signals in parallel via `Promise.allSettled` |
| `onFetchData({period, interval})` | Re-fetch OHLCV only on period/interval change |
| `lastVal(arr)` | Walk backward through SMA/EMA array to find last non-null value |
| `initialInvested` | Computed: `shares × buy_price` from position data (no extra API call) |

### `frontend/src/views/News.vue`
| Function | Purpose |
|----------|---------|
| `fetchSearchHistory()` | Load history chips for the toggle row |
| `loadPortfolioNews()` | Auto-load news for up to 8 portfolio tickers on mount |
| `addTickerNews(ticker)` | Fetch + merge news for a ticker, mark it loaded |
| `removeTickerNews(ticker)` | Filter out articles by source_ticker, untrack from loadedTickers |
| `toggleTicker(ticker)` | Remove if loaded, add if not |
| `refreshNews()` | Re-fetch all loaded tickers, full replace (not merge), update lastRefreshed |
| `mergeNews(incoming)` | De-duplicate by title, sort newest-first |
| `onSearchType(text)` | Debounced autocomplete |

### `frontend/src/views/Portfolio.vue`
| Function | Purpose |
|----------|---------|
| `fetchPositions()` | Load positions with live P&L |
| `lookupTicker()` | Auto-fill company_name on ticker blur (1d/1d fetch) |
| `savePosition()` | Validate + POST new position (buy_date set server-side) |
| `deletePosition(id)` | DELETE by ID + refresh |
| `saveEdit()` | PATCH shares/buy_price/notes — ticker is immutable |

### `frontend/src/App.vue`
| Function | Purpose |
|----------|---------|
| `fetchMarkets()` | GET /stocks/markets → fills `markets` ref; called on mount + every 15s |
| `tick(ts)` | rAF callback: decrements `offset` by SPEED px/s, resets seamlessly after one copy width |

### `backend/app/routes/stocks.py` — markets
| Function | Purpose |
|----------|---------|
| `_is_trading_hours()` | True if 7 AM–8 PM ET Mon–Fri (uses `America/New_York` for DST safety) |
| `_fetch_market_item(label, sym, is_futures)` | Fetch 5d daily history for one symbol, return price + session change |
| `get_markets()` | Selects spot vs futures tickers based on `_is_trading_hours()`, runs 8 fetches in parallel |

### `frontend/src/components/Signals.vue`
| Function | Purpose |
|----------|---------|
| `crossLabel(v)` / `crossColor(v)` | Golden/death cross → display label + chip color |
| `trendColor(v)` | bullish/bearish → success/error chip color |
| `volColor(v)` | Volume signal string (contains 'bullish'/'bearish') → chip color |

### `backend/app/routes/recommendations.py`
| Function | Purpose |
|----------|---------|
| `_last_val(arr)` | Walk backward through SMA/EMA list to find last non-None value |
| `get_market_pulse()` | Signal analysis for SPY/QQQ/DIA (direction + buy%) + live futures prices for ES=F/NQ=F/YM=F; all 6 fetched in parallel; must stay above `/{ticker}` route |
| `get_recommendations()` | Collect tickers from Portfolio + WatchlistItem, run signal engine in parallel, filter buy_pct ≥ 50, return top 10 sorted by buy_pct desc; each item includes entry/stop/target from Fibonacci |

### `frontend/src/views/Recommendations.vue`
| Function | Purpose |
|----------|---------|
| `fetchRecs()` | GET /recommendations/ → fills `recs` ref |
| `crossChip(val)` | sma_cross / ema_cross string → `{label, color}` for the why chip |
| `volChip(val)` | volume signal string → `{label, color, show}` or null when normal |
| `newsChip(bd)` | breakdown dict → `{label, color}` based on good vs bad news counts |
| `buyChipColor(pct)` | buy_pct → 'success' (≥ 65) or 'warning' |
