# Features — Local Stock Analyzer & Portfolio Tracker

## Dashboard

### Search
- Type any ticker symbol and press Enter or click the search icon
- Search history chips appear below the search bar — click any chip to re-load that stock instantly
- Each chip shows ticker + company name

### Info Panel (left)
- Company name and ticker
- Current price with dollar and percent change from previous close
- **My Position card** — if the searched stock is in your portfolio, shows shares held, avg cost, current market value, and total P&L (green/red)
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

**Overlay toggles** (chips, colored to match chart line):
| Toggle | Color | Default |
|--------|-------|---------|
| SMA 20 | Blue `#2196F3` | ON |
| SMA 50 | Orange `#FF9800` | ON |
| SMA 200 | Cyan `#26C6DA` | OFF |
| EMA 20 | Purple `#9C27B0` | OFF |
| EMA 50 | Light purple `#AB47BC` | OFF |
| Fib | Amber `#FFA726` | ON |
| News | Green `#4CAF50` | ON |
| Vol | Blue-grey `#546E7A` | ON |

- ON state: solid filled chip in the line's color
- OFF state: text-only chip in grey

**Fibonacci levels** — 7 dashed horizontal price lines (0%, 23.6%, 38.2%, 50%, 61.8%, 78.6%, 100%) calculated from the 60-day high/low

**News markers** — arrows plotted on candles where news was published (green arrow up = positive, red arrow down = negative, grey circle = neutral); deduplicated to one marker per day (highest absolute sentiment score)

### Signals
- Composite Buy / Sell / Hold percentages
- Breakdown: price vs SMA20, price vs SMA50, SMA cross, EMA cross, news sentiment, volume signal

### News Feed
- Latest headlines with publisher, timestamp, and sentiment chip (Good / Bad / Neutral)

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

## Constraints & Non-Features

- No cloud infrastructure, no Docker, no authentication
- No real-time streaming — data fetched on demand via `yfinance`
- No buy/sell execution — portfolio is manually entered for tracking only
- No Tailwind, no custom CSS, no `<style>` blocks
