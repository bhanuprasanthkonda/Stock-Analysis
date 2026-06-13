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
| SMA 20 | `#2196F3` |
| SMA 50 | `#FF9800` |
| SMA 200 | `#26C6DA` |
| EMA 20 | `#9C27B0` |
| EMA 50 | `#AB47BC` |
| Vol | `#546E7A` |
| Fib | `#FFA726` |
| News | `#4CAF50` |

---

## Routes

| Route | View | Notes |
|-------|------|-------|
| `/dashboard` | Dashboard.vue | accepts `?ticker=` query param to auto-search |
| `/portfolio` | Portfolio.vue | clicking a ticker navigates to `/dashboard?ticker=X` |
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
