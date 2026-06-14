# Features — Local Stock Analyzer & Portfolio Tracker

## App Bar — Market Ticker

8 market items are displayed statically across the full width of the app bar.

**During trading hours (7 AM – 8 PM ET, Mon–Fri) — cash indices:**
S&P 500 (`^GSPC`) · Dow 30 (`^DJI`) · Nasdaq (`^IXIC`) · Russell 2000 (`^RUT`) · VIX · Gold · Bitcoin · Crude Oil

**Outside trading hours (8 PM – 7 AM ET, weekends) — futures:**
S&P Fut. (`ES=F`) · Dow Fut. (`YM=F`) · Nasdaq Fut. (`NQ=F`) · Russell Fut. (`RTY=F`) · VIX · Gold · Bitcoin · Crude Oil

**Each item shows:** name, price (comma-formatted, 2 dp), and session change (+/−value  +/−%) in green/red.

**Mode indicator:** A label to the left of the items shows "Markets" (globe icon) during session, "Futures" (clock icon, amber) after hours.

**Behavior:**
- Items are static — they fill the app bar width equally with no scrolling
- Market data refreshes from backend every **15 seconds**
- Mode switch (spot ↔ futures) is determined server-side using ET timezone with correct DST handling (`America/New_York`)
- Shows a skeleton loader while the first fetch is in progress
- Degrades gracefully (bar stays empty) if the backend is unreachable

---

## Dashboard

### Search
- Type any ticker symbol and press Enter or click the search icon
- Search history chips appear below the search bar — click any chip to re-load that stock instantly
- Each chip shows ticker + company name

### Info Panel (left)
- Company name and ticker
- Current price with dollar and percent change from previous close
- **My Position card** — if the searched stock is in your portfolio, shows shares held, avg cost, initial amount invested (shares × avg cost), current market value, and total P&L $ + % (green/red)
- Today's price range bar (low → current → high)
- 52-week range bar
- Key stats: open, prev close, day volume, avg volume, market cap
- Current values for all five moving averages (color-coded to match chart lines)

### Chart (right) — powered by TradingView `lightweight-charts`
- Candlestick chart with green/red wicks
- Volume bars at the bottom 20% of the chart (green = up day, red = down day)

**Period selector** (10 buttons):
`1D` `1W` `1M` `3M` `6M` `YTD` `1Y` `2Y` `5Y` `MAX`

**Candle interval selector** (7 buttons):
`1m` `5m` `15m` `30m` `1h` `1D` `1W`

Switching period auto-selects a sensible default interval (e.g. 1D → 5m, 1W → 1h, 1M+ → 1d, MAX → 1wk).

**Infinite scroll (continuous history)** — panning left past the start of the current dataset automatically fetches and prepends the next broader period:
`1D → 5D → 1M → 3M → 6M → 1Y → 2Y → 5Y → MAX`
The view position is preserved so you see the newly loaded bars without jumping. A "Loading history…" chip appears in the chart header while the fetch is in flight. Expansion silently stops at MAX (no further history available).

**Overlay toggles** (chips, colored to match chart line):
| Toggle | Color | Default |
|--------|-------|---------|
| SMA 50 | Orange `#FF9800` | ON |
| SMA 200 | Cyan `#26C6DA` | ON |
| EMA 50 | Pink `#E91E63` | OFF |
| EMA 100 | Deep orange `#FF7043` | OFF |
| EMA 150 | Green `#66BB6A` | OFF |
| EMA 200 | Purple `#9C27B0` | OFF |
| Fib | Amber `#FFA726` | ON |
| News | Green `#4CAF50` | ON |
| Vol | Blue-grey `#546E7A` | ON |

- ON state: solid filled chip in the line's color
- OFF state: text-only chip in grey

**Fibonacci levels** — 7 dashed horizontal price lines (0%, 23.6%, 38.2%, 50%, 61.8%, 78.6%, 100%) calculated from the 60-day high/low

**Trend lines** — automatically detected pivot-based trend lines drawn over the candles:
- **↑ Trend** (teal `#26A69A`) — uptrend support line connecting the most recent ascending pivot lows
- **↓ Trend** (red `#EF5350`) — downtrend resistance line connecting the most recent descending pivot highs
- Each line is extended (projected linearly) to the current date so you can see where support/resistance sits right now
- Pivot detection uses a ±10 candle window; works for any period/interval combination
- Both lines are togglable via chips in the chart header

**News markers** — arrows plotted on candles where news was published (green arrow up = positive, red arrow down = negative, grey circle = neutral); deduplicated to one marker per day (highest absolute sentiment score)

### Signals
- Composite Buy / Sell / Hold percentages
- Breakdown: price vs SMA20, price vs SMA50, SMA cross, EMA cross, news sentiment, volume signal

### News Feed
- Latest headlines with publisher, timestamp, and sentiment chip (Good / Bad / Neutral)
- Related ticker chips shown on each news card; clicking a ticker navigates to its Dashboard; each chip has an ✕ to dismiss it from that card

### Trade Setup

Stacked below the Signals card in the left column of the Dashboard. Provides Fibonacci-based entry/exit levels for the currently viewed stock.

**Best Entry** — the nearest Fibonacci support level at or below the current price, labeled with its retracement percentage. Falls back to current price if no lower support exists.

**My Entry Price (optional)** — a text field to override the entry price used for stop/target calculations. When left empty, all calculations use the live current price.

**Stop Loss** — the nearest Fibonacci level below the effective entry price, with its retracement percentage and % distance from entry shown in red.

**Target 1 (conservative)** — first Fibonacci resistance level above the effective entry price.

**Target 2 (aggressive)** — second Fibonacci resistance level above entry.

**Risk / Reward** — `(Target 1 − entry) / (entry − Stop Loss)`, shown as a color-coded chip:
- Green (≥ 2:1), Amber (1–2:1), Red (< 1:1)

All levels update instantly when a custom entry price is typed.

---

### ETF Holdings (ETFs and mutual funds only)
- Full-width table shown automatically when the searched ticker is an ETF or mutual fund
- Columns: rank (#), Symbol (clickable → opens that stock in the Dashboard), Name, Weight %
- Weight column includes a mini progress bar scaled to the largest holding
- Paginated (25 per page); shows "N holdings" chip in the card header

### Institutional Holders
- Table: institution name, shares, % outstanding, value, date reported

### Fibonacci List
- Compact list of all 7 Fibonacci price levels

---

## Portfolio

- Table of all positions with live prices fetched on page load
- Columns: Ticker (clickable → opens Dashboard), Company, Shares, Avg Cost, Current Price, Market Value, P&L $, P&L %
- P&L $ shown with +/- prefix; P&L % shown as colored chip (green / red)
- Clicking a ticker navigates directly to the Dashboard and auto-loads that stock

### Add Position dialog
- Ticker field — blur triggers auto-lookup of company name from backend
- Company Name — read-only, auto-filled from ticker lookup
- Shares and Buy Price fields
- Notes field (optional)
- Buy date auto-set to today server-side (not shown in UI)

---

## News

- Dedicated news aggregator page showing headlines across multiple tickers in one table
- Loads news for portfolio holdings automatically on page load
- Columns: Ticker (clickable → Dashboard), Headline (linked), Related tickers, Publisher, Sentiment chip, Date
- **Search history chips** — all previously searched tickers shown as chips; clicking a chip loads that ticker's news into the table; loaded tickers show a ✓ and turn solid-primary
- "Add ticker" autocomplete to add any ticker's news on demand
- **Refresh button** — re-fetches news for all currently loaded tickers and replaces stale articles; shows a spinner while loading
- **Auto-refresh** — news refreshes automatically every 5 minutes while the page is open
- **Last updated timestamp** — shown next to the page title after the first load/refresh
- "Clear" button resets the table and clears all loaded tickers
- Headlines deduplicated by title across tickers; sorted newest-first

---

## History

- Standalone page showing all previously searched tickers (most recent first)
- Columns: Ticker (clickable), Company Name, Searched At
- Each ticker has one entry only — re-searching a ticker moves it to the top
- Clicking a ticker or the View button navigates to Dashboard and loads that stock

---

## Technical Indicators (backend `engine.py`)

| Indicator | Description |
|-----------|-------------|
| SMA | Simple moving average over N closes |
| EMA | Exponential moving average, seeded with SMA |
| Fibonacci | 7 retracement levels from 60-day high/low |
| VADER sentiment | Per-headline compound score → Good / Bad / Neutral |
| Signal engine | Composite of SMA/EMA crosses, price vs MA, news ratio, volume trend |

---

## Code Documentation

All functions in the backend and frontend have inline comments explaining:
- What the function does and why (not just what the name already says)
- Non-obvious invariants (e.g. why EMA is seeded with SMA, why loadedTickers needs a new Set for reactivity)
- Edge cases and fallback behavior

A full function index is maintained in `CLAUDE.md` under the **Function Reference** section.

---

## Constraints & Non-Features

- No cloud infrastructure, no Docker, no authentication
- No real-time streaming — data fetched on demand via `yfinance`
- No buy/sell execution — portfolio is manually entered for tracking only
- No Tailwind, no custom CSS, no `<style>` blocks
