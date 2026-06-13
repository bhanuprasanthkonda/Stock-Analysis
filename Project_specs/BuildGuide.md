# Build Guide — Rebuild From Scratch

> Hand this file to Claude Code and say: "Build me a local stock analyzer following this guide." Every architectural decision, dependency, and pattern is documented here so the entire project can be reconstructed without the original source.

---

## What You Are Building

A local-first stock analysis + portfolio tracker. No cloud, no Docker, no subscriptions, no auth. Runs entirely on the user's machine. Search any stock ticker to see candlestick charts, technical indicators, news sentiment, and institutional holders. Track a manual portfolio with live P&L.

**Tech stack:**
- Backend: Python 3 + FastAPI + SQLite + yfinance + nltk VADER
- Frontend: Vue 3 (Composition API) + Vuetify 3 + lightweight-charts v4 + axios

**Strict constraints:**
- No Tailwind CSS
- No custom CSS files or `<style>` blocks in Vue files — Vuetify only
- Vue 3 `<script setup>` only (no Options API)
- No Docker, no auth, no cloud

---

## Phase 1 — Project Scaffolding

### Directory structure to create
```
stock_analysis/
├── CLAUDE.md
├── start.sh
├── start.bat
├── .gitignore
├── backend/
│   └── app/
│       └── routes/
└── frontend/   ← scaffold with Vite
```

### .gitignore
```
backend/venv/
backend/stocks.db
__pycache__/
*.pyc
frontend/node_modules/
frontend/dist/
.env
```

### Backend setup
```bash
mkdir -p backend/app/routes
touch backend/app/__init__.py backend/app/routes/__init__.py
cd backend
python3 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn yfinance pandas numpy sqlalchemy nltk
pip freeze > requirements.txt
```

### Frontend setup
```bash
npm create vite@latest frontend -- --template vue
cd frontend
npm install
npm install vuetify vue-router axios lightweight-charts @mdi/font
```

---

## Phase 2 — Backend Core

### `backend/app/database.py`
```python
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "stocks.db")
DATABASE_URL = f"sqlite:///{os.path.abspath(DB_PATH)}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

class Base(DeclarativeBase):
    pass

def init_db():
    from app import models  # noqa
    Base.metadata.create_all(bind=engine)
    # Add columns missing from existing databases (no Alembic needed)
    with engine.connect() as conn:
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(search_history)")).fetchall()]
        if 'company_name' not in cols:
            conn.execute(text("ALTER TABLE search_history ADD COLUMN company_name VARCHAR"))
            conn.commit()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### `backend/app/models.py`
```python
from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from app.database import Base

class Portfolio(Base):
    __tablename__ = "portfolio"
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, nullable=False, index=True)
    company_name = Column(String, nullable=True)
    shares = Column(Float, nullable=False)
    buy_price = Column(Float, nullable=False)
    buy_date = Column(String, nullable=False)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

class SearchHistory(Base):
    __tablename__ = "search_history"
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, nullable=False, index=True)
    company_name = Column(String, nullable=True)
    searched_at = Column(DateTime, server_default=func.now())

class ReadStock(Base):
    __tablename__ = "read_stocks"
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, nullable=False, index=True)
    marked_read_at = Column(DateTime, server_default=func.now())
```

### `backend/app/schemas.py`
Key schemas to define:
- `PortfolioCreate` / `PortfolioOut` — `buy_date: Optional[str] = None`
- `OHLCVPoint` — `date: int` (Unix seconds, NOT a date string)
- `StockResponse` — includes `week_52_high`, `week_52_low`, `day_volume`, `avg_volume`, `sma_200`
- `PositionOut` — extends portfolio with `current_price`, `market_value`, `pnl_dollar`, `pnl_pct`
- `SearchHistoryOut` — includes `company_name`
- `NewsItem` — `published_at: str`, `sentiment: str`, `compound_score: float`
- `SignalsResponse` — `buy`, `sell`, `hold` floats + `breakdown` dict
- `FibonacciLevels` — `high_60d`, `low_60d`, `levels: dict[str, float]`

### `backend/app/engine.py`
Functions to implement:
```python
def calculate_sma(closes: list[float], period: int) -> list[Optional[float]]
def calculate_ema(closes: list[float], period: int) -> list[Optional[float]]
def calculate_fibonacci(high: float, low: float) -> dict[str, float]
    # levels: 0%, 23.6%, 38.2%, 50%, 61.8%, 78.6%, 100%

def extract_ohlcv(df: pd.DataFrame) -> list[dict]:
    # CRITICAL: date must be int(ts.timestamp()) — Unix seconds, not string

def get_60day_high_low(df: pd.DataFrame) -> tuple[float, float]

def score_headline(text: str) -> tuple[str, float]:
    # uses nltk VADER → returns ('good'|'bad'|'neutral', compound_score)

def calculate_signals(...) -> dict:
    # composite of: price vs SMA20, price vs SMA50, SMA cross, EMA cross,
    # news sentiment ratio, volume trend → buy/sell/hold percentages
```

### `backend/app/main.py`
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.database import init_db
from app.routes import portfolio, stocks

@asynccontextmanager
async def lifespan(app):
    init_db()
    yield

app = FastAPI(title="Local Stock Analyzer", lifespan=lifespan)
app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174",
                   "http://127.0.0.1:5173", "http://127.0.0.1:5174"],
    allow_methods=["*"], allow_headers=["*"])
app.include_router(portfolio.router)
app.include_router(stocks.router)
```

### `backend/app/routes/stocks.py`
Key points:
- Route: `GET /stocks/{ticker}?period=1y&interval=1d`
- Use `_PERIOD_TO_YF` dict to map UI period keys (`1d`, `1w`, `1mo`…) to yfinance strings
- Use `t.fast_info.year_high` and `year_low` (NOT `fifty_two_week_high/low` — those don't exist)
- Log search: delete old SearchHistory row for ticker, insert fresh one (deduplication)
- `company_name = info.get("longName") or info.get("shortName") or ticker` — resolve BEFORE using `info`

### `backend/app/routes/portfolio.py`
Key endpoints:
- `GET /portfolio/positions` — fetches live prices via `yf.Ticker(tkr).fast_info.last_price`, computes P&L
- `GET /portfolio/history` — ordered by `searched_at desc`, limited to 20 (already unique per ticker)
- `POST /portfolio/` — auto-fills `buy_date = date.today().isoformat()` if not provided

---

## Phase 3 — Frontend Setup

### `frontend/src/plugins/vuetify.js`
```js
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import '@mdi/font/css/materialdesignicons.css'
import 'vuetify/styles'

export default createVuetify({
  components, directives,
  theme: {
    defaultTheme: 'dark',
    themes: {
      dark: { dark: true, colors: { primary: '#2196F3', secondary: '#FF9800' } }
    }
  }
})
```

### `frontend/src/main.js`
```js
import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import vuetify from './plugins/vuetify'
import App from './App.vue'
import Dashboard from './views/Dashboard.vue'
import Portfolio from './views/Portfolio.vue'
import History from './views/History.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', component: Dashboard },
    { path: '/portfolio', component: Portfolio },
    { path: '/history', component: History },
  ],
})
createApp(App).use(vuetify).use(router).mount('#app')
```

### `frontend/src/api.js`
```js
import axios from 'axios'
export default axios.create({ baseURL: 'http://localhost:8000' })
```

### `frontend/src/App.vue`
Navigation drawer (220px wide, permanent) with three nav items:
- Dashboard → `/dashboard` icon: `mdi-view-dashboard-outline`
- Portfolio → `/portfolio` icon: `mdi-briefcase-outline`
- History   → `/history`   icon: `mdi-history`

Top app bar + `<router-view />` in `<v-main>`.

---

## Phase 4 — Dashboard View

**Layout:** `v-row` with left info panel (`md="4"`) and right chart (`md="8"`).

**Search bar** with history chips below it:
- Chips come from `GET /portfolio/history`
- Clicking a chip calls `searchStock(ticker)`
- `onMounted`: if `route.query.ticker` exists, auto-search it (for navigation from Portfolio)

**Left info panel** contains:
1. Ticker + company name
2. Current price + change (dollar + percent)
3. **My Position card** — if user holds this stock, show shares, avg cost, market value, P&L (colored tonal card)
4. Today's range `v-progress-linear`
5. 52-week range `v-progress-linear`
6. Key stats grid (open, prev close, day volume, avg volume, market cap)
7. Moving averages current values with hex color labels

**Right chart** — `StockChart.vue` receives:
```
:ohlcv :sma20 :sma50 :sma200 :ema20 :ema50 :fibonacci :news :period :interval
@fetch-data="onFetchData"
```

Period/interval are refs in Dashboard — passed as props to StockChart and updated via `fetch-data` emit. This keeps the selected button highlighted even when the chart component remounts.

---

## Phase 5 — StockChart Component

Uses `lightweight-charts` v4 (TradingView). Key patterns:

```js
import { createChart, ColorType, CrosshairMode, LineStyle } from 'lightweight-charts'

// Volume on hidden overlay scale (bottom 20% of chart)
volS = chart.addHistogramSeries({ priceScaleId: '' })
chart.priceScale('').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } })
// Candles shifted up to leave room for volume
chart.applyOptions({ rightPriceScale: { scaleMargins: { top: 0.05, bottom: 0.22 } } })

// Fibonacci as price lines on the candlestick series
candleS.createPriceLine({ price, color, lineStyle: LineStyle.Dashed, title: '38.2%' })

// News as markers (must be sorted by time)
candleS.setMarkers([{ time: unixSeconds, position: 'aboveBar', color, shape: 'arrowUp' }])

// Responsive resize
new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth })).observe(el)
```

**Period selector** — 10 buttons: `1D 1W 1M 3M 6M YTD 1Y 2Y 5Y MAX`  
**Interval selector** — 7 buttons: `1m 5m 15m 30m 1h 1D 1W`  
**DEFAULT_INTERVAL map** — switching period picks a sensible default interval  
**Overlay toggles** — 8 chips: SMA20, SMA50, SMA200, EMA20, EMA50, Fib, News, Vol

Chip pattern: `variant="flat"` + hex color when ON, `variant="text" color="grey"` when OFF.

---

## Phase 6 — Portfolio & History Views

### Portfolio.vue
- Table: Ticker (clickable → `router.push('/dashboard?ticker=X')`), Company, Shares, Avg Cost, Cur Price, Mkt Value, P&L $, P&L %
- Add Position dialog: Ticker field with `@blur` → auto-fetch company name from `/stocks/{ticker}?period=1d&interval=1d`; Company Name field is `readonly` with `:loading="lookingUp"`

### History.vue
- Table: Ticker (clickable), Company, Searched At
- Same navigation pattern as Portfolio

---

## Common Pitfalls to Avoid

| Mistake | Correct approach |
|---------|-----------------|
| `fast.fifty_two_week_high` | `fast.year_high` |
| `OHLCVPoint.date` as string | Must be `int(ts.timestamp())` |
| Local `activePeriod` ref in StockChart | Pass as prop from Dashboard |
| Installing apexcharts | Use `lightweight-charts` v4 |
| `<style>` blocks in Vue files | Not allowed — Vuetify utility classes only |
| Reading `info` before defining it | Call `info = t.info` before using `company_name = info.get(...)` |
| Not deduplicating search history | Delete old row before inserting new one |
