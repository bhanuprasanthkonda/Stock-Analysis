# Technical Specification — Local Stock Analyzer & Portfolio Tracker

## Architecture

| Layer | Technology |
|-------|-----------|
| Frontend | Vue 3 (Composition API) + Vuetify 3 |
| Backend | Python 3 + FastAPI |
| Database | SQLite (`backend/stocks.db`) |
| Financial data | `yfinance` |
| Charting | `lightweight-charts` v4 (TradingView) |
| Sentiment | `nltk` VADER |

---

## Code Style Constraints (Strict)

- **No Tailwind CSS** — never install or use it
- **No custom CSS** — no `.css`/`.scss` files and no `<style>` blocks in Vue files
- **Vuetify-only** — all layout, spacing, color, and responsive behaviour via Vuetify props and utility classes (`v-row`, `v-col`, `pa-4`, `text-success`, etc.)
- **Vue 3 Composition API only** — `<script setup>` everywhere, no Options API

---

## Directory Structure

```
stock_analysis/
├── README.md
├── Project_specs/
│   ├── Spec.md          ← this file
│   └── features.md
├── backend/
│   ├── venv/
│   ├── requirements.txt
│   ├── stocks.db
│   └── app/
│       ├── main.py         — FastAPI entrypoint + CORS + lifespan
│       ├── database.py     — SQLAlchemy engine, Base, SessionLocal, init_db
│       ├── models.py       — ORM models (Portfolio, SearchHistory, ReadStock)
│       ├── schemas.py      — Pydantic schemas (request / response)
│       ├── engine.py       — SMA, EMA, Fibonacci, OHLCV extraction, sentiment, signals
│       └── routes/
│           ├── stocks.py   — /stocks/{ticker}, /news, /signals
│           └── portfolio.py — /portfolio CRUD + /positions P&L + /history
└── frontend/
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── main.js
        ├── App.vue
        ├── api.js
        ├── plugins/vuetify.js
        ├── components/
        │   ├── StockChart.vue   — lightweight-charts candlestick + overlays
        │   ├── NewsCard.vue     — sentiment-tagged news items
        │   └── Signals.vue     — Buy/Sell/Hold gauge
        └── views/
            ├── Dashboard.vue   — search + info panel + chart
            ├── Portfolio.vue   — positions table
            └── History.vue     — search history table
```

---

## Database Schema

### `portfolio`
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| ticker | TEXT | |
| company_name | TEXT | nullable |
| shares | REAL | |
| buy_price | REAL | |
| buy_date | TEXT | ISO-8601, auto-set to today if omitted |
| notes | TEXT | nullable |
| created_at | DATETIME | server default |

### `search_history`
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| ticker | TEXT | one row per ticker (upserted on each search) |
| company_name | TEXT | nullable |
| searched_at | DATETIME | server default |

### `read_stocks`
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| ticker | TEXT | |
| marked_read_at | DATETIME | server default |

---

## API Endpoints

### Stocks
| Method | Path | Description |
|--------|------|-------------|
| GET | `/stocks/{ticker}?period=1y&interval=1d` | OHLCV + indicators + Fibonacci + holders |
| GET | `/stocks/{ticker}/news` | Latest news with VADER sentiment |
| GET | `/stocks/{ticker}/signals` | Buy/Sell/Hold composite score |

**Period keys:** `1d` `1w` `1mo` `3mo` `6mo` `ytd` `1y` `2y` `5y` `max`  
**Interval keys:** `1m` `5m` `15m` `30m` `1h` `1d` `1wk`

### Portfolio
| Method | Path | Description |
|--------|------|-------------|
| GET | `/portfolio/positions` | All positions with live P&L |
| POST | `/portfolio/` | Add position |
| DELETE | `/portfolio/{id}` | Remove position |
| GET | `/portfolio/history` | Deduplicated search history (latest 20) |

---

## Key Data Types

### `OHLCVPoint`
```python
date: int      # Unix timestamp in seconds (works for daily + intraday)
open: float
high: float
low: float
close: float
volume: int
```

### `StockResponse`
Includes: `ticker`, `company_name`, `current_price`, `previous_close`, `day_high`, `day_low`, `day_volume`, `avg_volume`, `market_cap`, `week_52_high`, `week_52_low`, `ohlcv`, `sma_20`, `sma_50`, `sma_200`, `ema_20`, `ema_50`, `fibonacci`, `institutional_holders`

### `PositionOut`
Includes all portfolio fields plus live: `current_price`, `market_value`, `pnl_dollar`, `pnl_pct`
