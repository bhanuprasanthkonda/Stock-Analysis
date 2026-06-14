<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'
import StockChart from '../components/StockChart.vue'
import Signals from '../components/Signals.vue'
import NewsCard from '../components/NewsCard.vue'

const route = useRoute()

const tickerInput   = ref(null)   // selected/searched ticker value
const searchInput   = ref('')     // raw text in the autocomplete input
const suggestions   = ref([])
const suggesting    = ref(false)
let suggestTimer    = null

const currentPeriod   = ref('1y')
const currentInterval = ref('1d')
const loading = ref(false)
const error = ref('')
const stock = ref(null)
const news = ref([])
const signals = ref(null)
const searchHistory = ref([])
const historyLimit = ref(10)   // how many recent-search chips to show; null = show all
const myPosition = ref(null)
const entryInput = ref('')

const toast = ref(false)
const toastMsg = ref('')
function showToast(msg) { toastMsg.value = msg; toast.value = true }

// Loads recent search history chips shown below the search bar. Non-critical —
// failure is silently ignored so it never blocks the main stock load.
async function fetchHistory() {
  try {
    const res = await api.get('/portfolio/history')   // limit=0 → all rows
    searchHistory.value = res.data
  } catch { /* non-critical */ }
}

// Fetches all positions and finds the one matching the currently searched ticker.
// Pulls the full positions list (with live P&L) rather than a single-ticker endpoint
// so we get the pre-calculated pnl_dollar and pnl_pct from the backend.
async function fetchMyPosition(ticker) {
  try {
    const res = await api.get('/portfolio/positions')
    myPosition.value = res.data.find(p => p.ticker === ticker) ?? null
  } catch {
    myPosition.value = null
  }
}

// On mount: pre-load history chips and auto-search if the URL has ?ticker=XYZ
// (used when navigating here from Portfolio or History pages).
onMounted(() => {
  fetchHistory()
  const t = route.query.ticker
  if (t) searchStock(String(t))
})

// ── Formatters ────────────────────────────────────────────────────────────────
const fmtPrice = v => v != null ? `$${Number(v).toFixed(2)}` : '—'
const fmtCap = v => {
  if (!v) return '—'
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`
  if (v >= 1e9)  return `$${(v / 1e9).toFixed(2)}B`
  if (v >= 1e6)  return `$${(v / 1e6).toFixed(2)}M`
  return `$${v.toLocaleString()}`
}
const fmtVol = v => {
  if (!v) return '—'
  if (v >= 1e9) return `${(v / 1e9).toFixed(2)}B`
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`
  return v.toLocaleString()
}

// ── Fetch ─────────────────────────────────────────────────────────────────────

// Debounced autocomplete — fires 300ms after the user stops typing to avoid
// flooding the backend with a request for every keystroke.
function onSearchType(text) {
  if (!text || text.length < 2) { suggestions.value = []; return }
  clearTimeout(suggestTimer)
  suggestTimer = setTimeout(async () => {
    suggesting.value = true
    try {
      const res = await api.get(`/stocks/search?q=${encodeURIComponent(text)}`)
      suggestions.value = res.data.map(r => ({ ticker: r.ticker, label: `${r.ticker} — ${r.name}` }))
    } catch { suggestions.value = [] }
    finally { suggesting.value = false }
  }, 300)
}

// Main search handler. Fires three requests in parallel via Promise.allSettled so
// a missing-news or missing-signals response never blocks the stock data from rendering.
// Only a failed stock fetch shows an error; news/signals degrade to empty state.
// The ticker is extracted before the '—' separator in case the user picks from
// the autocomplete dropdown (which labels items as "AAPL — Apple Inc.").
async function searchStock(sym) {
  const ticker = String(sym || searchInput.value || '').trim().toUpperCase().split('—')[0].trim()
  if (!ticker) return
  tickerInput.value = ticker
  searchInput.value = ticker
  suggestions.value = []
  currentPeriod.value   = '1y'
  currentInterval.value = '1d'
  loading.value = true
  error.value = ''
  stock.value = null
  news.value = []
  signals.value = null
  myPosition.value = null
  entryInput.value = ''
  try {
    const [stockRes, newsRes, sigRes] = await Promise.allSettled([
      api.get(`/stocks/${ticker}?period=1y&interval=1d`),
      api.get(`/stocks/${ticker}/news`),
      api.get(`/stocks/${ticker}/signals`),
    ])
    if (stockRes.status === 'rejected') {
      const e = stockRes.reason
      error.value = !e.response
        ? `Cannot reach backend (http://localhost:8000). Is the server running?`
        : e.response.data?.detail ?? `Server error ${e.response.status} for "${ticker}".`
    } else {
      stock.value = stockRes.value.data
      news.value = newsRes.status === 'fulfilled' ? newsRes.value.data : []
      signals.value = sigRes.status === 'fulfilled' ? sigRes.value.data : null
      fetchHistory()
      fetchMyPosition(ticker)
    }
  } finally {
    loading.value = false
  }
}

// ── Infinite-scroll history expansion ────────────────────────────────────────

// Each period maps to the next broader period to fetch when the user pans left
// past the beginning of the current dataset.
const NEXT_PERIOD = {
  '1d': '5d', '5d': '1mo', '1mo': '3mo', '3mo': '6mo',
  '6mo': '1y', '1y': '2y', '2y': '5y', '5y': 'max',
}

const isExpandingHistory = ref(false)

// Called when StockChart emits 'load-more' (user panned to the left edge).
// Fetches the next broader period using the lightweight /ohlcv endpoint and
// merges it into the existing stock data — company info, news, signals unchanged.
async function handleLoadMore() {
  if (isExpandingHistory.value || !stock.value) return
  const nextPeriod = NEXT_PERIOD[currentPeriod.value]
  if (!nextPeriod) return  // already at max — nothing more to load

  isExpandingHistory.value = true
  try {
    const res = await api.get(
      `/stocks/${stock.value.ticker}/ohlcv?period=${nextPeriod}&interval=${currentInterval.value}`
    )
    const d = res.data
    // Merge chart fields in-place; company info, holders, news, signals are untouched.
    stock.value = {
      ...stock.value,
      ohlcv:       d.ohlcv,
      sma_50:      d.sma_50,
      sma_200:     d.sma_200,
      ema_50:      d.ema_50,
      ema_100:     d.ema_100,
      ema_150:     d.ema_150,
      ema_200:     d.ema_200,
      fibonacci:   d.fibonacci,
      trend_lines: d.trend_lines,
    }
    currentPeriod.value = nextPeriod
  } catch {
    // Silently ignore (e.g. interval not supported for the requested period)
  } finally {
    isExpandingHistory.value = false
  }
}

// Called by StockChart when the user selects a different period or candle interval.
// Loads new chart data in the background — the existing chart stays visible while
// the request is in flight. Only swaps in new data on success; on failure shows a
// toast and reverts the period/interval selectors to what was displayed before.
async function onFetchData({ period, interval }) {
  const sym = String(tickerInput.value || '').trim().toUpperCase()
  if (!sym) return
  const prevPeriod   = currentPeriod.value
  const prevInterval = currentInterval.value
  currentPeriod.value   = period
  currentInterval.value = interval
  loading.value = true
  try {
    const res = await api.get(`/stocks/${sym}?period=${period}&interval=${interval}`)
    // Merge only chart fields — company info, news, signals, holders are unchanged
    stock.value = {
      ...stock.value,
      ohlcv:       res.data.ohlcv,
      sma_50:      res.data.sma_50,
      sma_200:     res.data.sma_200,
      ema_50:      res.data.ema_50,
      ema_100:     res.data.ema_100,
      ema_150:     res.data.ema_150,
      ema_200:     res.data.ema_200,
      fibonacci:   res.data.fibonacci,
      trend_lines: res.data.trend_lines,
    }
  } catch (e) {
    currentPeriod.value   = prevPeriod
    currentInterval.value = prevInterval
    const detail = e.response?.data?.detail
    showToast(detail ?? `"${period} / ${interval}" is not available for ${sym}.`)
  } finally {
    loading.value = false
  }
}

// ── Computed helpers ──────────────────────────────────────────────────────────
const priceChange    = computed(() => stock.value ? stock.value.current_price - stock.value.previous_close : 0)
const priceChangePct = computed(() => stock.value?.previous_close ? (priceChange.value / stock.value.previous_close * 100) : 0)
const changeColor    = computed(() => priceChange.value >= 0 ? 'text-success' : 'text-error')
const changeSign     = computed(() => priceChange.value >= 0 ? '+' : '')

// Today's open comes from the last OHLCV candle since yfinance doesn't expose it directly.
const todayOpen = computed(() => stock.value?.ohlcv?.slice(-1)[0]?.open ?? null)

// SMA/EMA arrays start with leading nulls (one per missing period). Walk backward
// to find the most recent non-null value for display in the info panel.
const lastVal = arr => {
  if (!arr?.length) return null
  for (let i = arr.length - 1; i >= 0; i--) {
    if (arr[i] != null) return arr[i]
  }
  return null
}


const sma50Last  = computed(() => lastVal(stock.value?.sma_50))
const sma200Last = computed(() => lastVal(stock.value?.sma_200))
const ema50Last  = computed(() => lastVal(stock.value?.ema_50))
const ema100Last = computed(() => lastVal(stock.value?.ema_100))
const ema150Last = computed(() => lastVal(stock.value?.ema_150))
const ema200Last = computed(() => lastVal(stock.value?.ema_200))

// Initial cost basis — computed client-side from existing position data, no extra API call needed.
const initialInvested = computed(() =>
  myPosition.value ? myPosition.value.shares * myPosition.value.buy_price : null
)

const dayRangePct = computed(() => {
  const s = stock.value
  if (!s?.day_low || !s?.day_high || !s?.current_price) return 0
  const range = s.day_high - s.day_low
  return range ? Math.min(100, Math.max(0, Math.round(((s.current_price - s.day_low) / range) * 100))) : 0
})

const weekRangePct = computed(() => {
  const s = stock.value
  if (!s?.week_52_low || !s?.week_52_high || !s?.current_price) return 0
  const range = s.week_52_high - s.week_52_low
  return range ? Math.min(100, Math.max(0, Math.round(((s.current_price - s.week_52_low) / range) * 100))) : 0
})

// ── Trade Setup ───────────────────────────────────────────────────────────────

// Fibonacci levels sorted ascending by price (lowest first).
// Backend returns {"0": 60d-high, "23.6": ..., "100": 60d-low} — 0%=top, 100%=bottom.
const fibSorted = computed(() => {
  if (!stock.value?.fibonacci?.levels) return []
  return Object.entries(stock.value.fibonacci.levels)
    .map(([pct, price]) => ({ pct, price }))
    .sort((a, b) => a.price - b.price)
})

// Nearest Fibonacci support at or below the current price — the preferred entry zone.
const suggestedEntry = computed(() => {
  const price = stock.value?.current_price
  if (!price || !fibSorted.value.length) return null
  const below = fibSorted.value.filter(l => l.price <= price)
  return below.length ? below[below.length - 1] : null
})

// Custom entry price if typed, otherwise current market price.
const effectiveEntry = computed(() => {
  const custom = parseFloat(entryInput.value)
  return custom > 0 ? custom : (stock.value?.current_price ?? null)
})

// Nearest Fibonacci level below the effective entry — acts as a stop-loss floor.
const stopLoss = computed(() => {
  const entry = effectiveEntry.value
  if (!entry || !fibSorted.value.length) return null
  const below = fibSorted.value.filter(l => l.price < entry - 0.005)
  return below.length ? below[below.length - 1] : null
})

// First Fibonacci resistance above the effective entry — conservative profit target.
const target1 = computed(() => {
  const entry = effectiveEntry.value
  if (!entry || !fibSorted.value.length) return null
  const above = fibSorted.value.filter(l => l.price > entry + 0.005)
  return above.length ? above[0] : null
})

// Second Fibonacci resistance above the effective entry — aggressive profit target.
const target2 = computed(() => {
  const entry = effectiveEntry.value
  if (!entry || !fibSorted.value.length) return null
  const above = fibSorted.value.filter(l => l.price > entry + 0.005)
  return above.length > 1 ? above[1] : null
})

// Risk/Reward ratio: potential gain to Target 1 vs. risk down to Stop Loss.
const riskReward = computed(() => {
  const entry = effectiveEntry.value
  if (!entry || !stopLoss.value || !target1.value) return null
  const risk = entry - stopLoss.value.price
  if (risk <= 0) return null
  return ((target1.value.price - entry) / risk).toFixed(1)
})

// % distance from `from` to `to`, always signed (e.g. "+3.20%" or "-1.80%").
const pctFrom = (from, to) => {
  if (!from) return null
  const pct = (to - from) / from * 100
  return (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%'
}

// ── Holders table ─────────────────────────────────────────────────────────────
const holdersHeaders = [
  { title: 'Institution',  key: 'holder' },
  { title: 'Shares',       key: 'shares' },
  { title: '% Out',        key: 'pct_out' },
  { title: 'Value (USD)',  key: 'value' },
  { title: 'Date Reported', key: 'date_reported' },
]

// ── ETF holdings table ────────────────────────────────────────────────────────
const etfHoldingsHeaders = [
  { title: '#',       key: 'rank',   width: '60px' },
  { title: 'Symbol',  key: 'symbol' },
  { title: 'Name',    key: 'name' },
  { title: 'Weight',  key: 'weight' },
]
</script>

<template>
  <v-container fluid class="pa-6">

    <!-- Search Row -->
    <v-row class="mb-1">
      <v-col cols="12" sm="7" md="5">
        <v-autocomplete
          v-model="tickerInput"
          v-model:search="searchInput"
          :items="suggestions"
          item-title="label"
          item-value="ticker"
          :return-object="false"
          no-filter
          clearable
          hide-no-data
          hide-details
          label="Search ticker or company name"
          placeholder="AAPL, Apple Inc, Tesla…"
          variant="outlined"
          density="comfortable"
          :loading="loading || suggesting"
          append-inner-icon="mdi-magnify"
          @update:search="onSearchType"
          @update:model-value="v => v && searchStock(v)"
          @keydown.enter.prevent="searchStock()"
          @click:append-inner="searchStock()"
        />
      </v-col>
    </v-row>

    <!-- Search History -->
    <v-row v-if="searchHistory.length" class="mb-3">
      <v-col cols="12">
        <!-- Label + count picker -->
        <div class="d-flex align-center flex-wrap ga-1 mb-2">
          <v-icon size="13" color="medium-emphasis">mdi-history</v-icon>
          <span class="text-overline text-medium-emphasis mr-2">Recent Searches</span>
          <v-chip
            v-for="n in [10, 20, 30, 50, null]"
            :key="n ?? 'all'"
            size="x-small"
            :variant="historyLimit === n ? 'flat' : 'text'"
            :color="historyLimit === n ? 'primary' : 'default'"
            @click="historyLimit = n"
          >{{ n ?? 'All' }}</v-chip>
        </div>
        <!-- Chips, sliced to the chosen limit -->
        <div class="d-flex flex-wrap ga-2">
          <v-chip
            v-for="h in (historyLimit ? searchHistory.slice(0, historyLimit) : searchHistory)"
            :key="h.ticker"
            size="small"
            variant="tonal"
            color="primary"
            @click="searchStock(h.ticker)"
          >
            <span class="font-weight-medium">{{ h.ticker }}</span>
            <span v-if="h.company_name" class="text-medium-emphasis ml-1 text-caption">· {{ h.company_name }}</span>
          </v-chip>
        </div>
      </v-col>
    </v-row>

    <!-- Error -->
    <v-row v-if="error" class="mb-2">
      <v-col cols="12">
        <v-alert type="error" variant="tonal" density="compact" :text="error" />
      </v-col>
    </v-row>

    <!-- Empty state -->
    <v-row v-if="!loading && !stock && !error" class="mt-10" justify="center">
      <v-col cols="12" class="text-center">
        <v-icon size="64" color="surface-variant">mdi-chart-candlestick</v-icon>
        <p class="text-h6 text-medium-emphasis mt-4">Search a ticker to get started</p>
        <p class="text-body-2 text-medium-emphasis">Try AAPL, TSLA, NVDA, SPY…</p>
      </v-col>
    </v-row>

    <template v-if="stock">

      <!-- ── Row 1: Info panel + Chart ─────────────────────────────────────── -->
      <v-row class="mb-4" align="stretch">

        <!-- Left info panel -->
        <v-col cols="12" md="4">
          <v-card rounded="lg" height="100%">
            <v-card-text class="pa-5">

              <!-- Ticker + company -->
              <p class="text-h5 font-weight-bold">{{ stock.ticker }}</p>
              <p class="text-body-2 text-medium-emphasis mb-3">{{ stock.company_name }}</p>

              <!-- Price + change -->
              <p class="text-h3 font-weight-bold mb-1">{{ fmtPrice(stock.current_price) }}</p>
              <span :class="changeColor" class="text-body-1 font-weight-medium">
                {{ changeSign }}{{ fmtPrice(priceChange) }}
                ({{ changeSign }}{{ priceChangePct.toFixed(2) }}%)
              </span>

              <!-- My position P&L (shown only if user holds this stock) -->
              <v-card v-if="myPosition" variant="tonal" :color="myPosition.pnl_dollar >= 0 ? 'success' : 'error'" rounded="lg" class="mt-3 pa-3">
                <p class="text-caption text-medium-emphasis mb-2">My Position · {{ myPosition.shares }} shares @ {{ fmtPrice(myPosition.buy_price) }}</p>
                <v-row no-gutters align="center" class="mb-1">
                  <v-col>
                    <p class="text-body-2 font-weight-medium">{{ fmtPrice(initialInvested) }}</p>
                    <p class="text-caption text-medium-emphasis">Invested</p>
                  </v-col>
                  <v-col class="text-right">
                    <p class="text-body-2 font-weight-medium">{{ fmtPrice(myPosition.market_value) }}</p>
                    <p class="text-caption text-medium-emphasis">Market value</p>
                  </v-col>
                </v-row>
                <v-divider class="my-2 opacity-20" />
                <v-row no-gutters align="center">
                  <v-col>
                    <p class="text-caption text-medium-emphasis">Total P&L</p>
                  </v-col>
                  <v-col class="text-right">
                    <p class="text-body-2 font-weight-bold">
                      {{ myPosition.pnl_dollar >= 0 ? '+' : '' }}{{ fmtPrice(myPosition.pnl_dollar) }}
                      ({{ myPosition.pnl_pct >= 0 ? '+' : '' }}{{ myPosition.pnl_pct?.toFixed(2) }}%)
                    </p>
                  </v-col>
                </v-row>
              </v-card>

              <v-divider class="my-4" />

              <!-- Today's Range -->
              <p class="text-caption text-medium-emphasis mb-2">Today's Range</p>
              <v-row no-gutters align="center" class="mb-3">
                <v-col cols="auto" class="text-caption text-error pr-2">{{ fmtPrice(stock.day_low) }}</v-col>
                <v-col>
                  <v-progress-linear
                    :model-value="dayRangePct"
                    rounded
                    height="5"
                    color="success"
                    bg-color="rgba(255,255,255,0.08)"
                  />
                </v-col>
                <v-col cols="auto" class="text-caption text-success pl-2">{{ fmtPrice(stock.day_high) }}</v-col>
              </v-row>

              <!-- 52-Week Range -->
              <p class="text-caption text-medium-emphasis mb-2">52-Week Range</p>
              <v-row no-gutters align="center" class="mb-4">
                <v-col cols="auto" class="text-caption text-error pr-2">{{ fmtPrice(stock.week_52_low) }}</v-col>
                <v-col>
                  <v-progress-linear
                    :model-value="weekRangePct"
                    rounded
                    height="5"
                    color="primary"
                    bg-color="rgba(255,255,255,0.08)"
                  />
                </v-col>
                <v-col cols="auto" class="text-caption text-success pl-2">{{ fmtPrice(stock.week_52_high) }}</v-col>
              </v-row>

              <v-divider class="mb-3" />

              <!-- Key stats -->
              <v-row no-gutters class="py-1">
                <v-col cols="6" class="text-caption text-medium-emphasis">Open</v-col>
                <v-col cols="6" class="text-caption text-right">{{ fmtPrice(todayOpen) }}</v-col>
              </v-row>
              <v-row no-gutters class="py-1">
                <v-col cols="6" class="text-caption text-medium-emphasis">Prev Close</v-col>
                <v-col cols="6" class="text-caption text-right">{{ fmtPrice(stock.previous_close) }}</v-col>
              </v-row>
              <v-row no-gutters class="py-1">
                <v-col cols="6" class="text-caption text-medium-emphasis">Day Volume</v-col>
                <v-col cols="6" class="text-caption text-right">{{ fmtVol(stock.day_volume) }}</v-col>
              </v-row>
              <v-row no-gutters class="py-1">
                <v-col cols="6" class="text-caption text-medium-emphasis">Avg Volume</v-col>
                <v-col cols="6" class="text-caption text-right">{{ fmtVol(stock.avg_volume) }}</v-col>
              </v-row>
              <v-row no-gutters class="py-1">
                <v-col cols="6" class="text-caption text-medium-emphasis">Market Cap</v-col>
                <v-col cols="6" class="text-caption text-right">{{ fmtCap(stock.market_cap) }}</v-col>
              </v-row>

              <v-divider class="my-3" />

              <!-- Moving averages -->
              <p class="text-caption text-medium-emphasis mb-2">Moving Averages</p>
              <v-row no-gutters class="py-1">
                <v-col cols="5" class="text-caption" style="color:#FF9800">SMA 50</v-col>
                <v-col cols="7" class="text-caption text-right">{{ fmtPrice(sma50Last) }}</v-col>
              </v-row>
              <v-row no-gutters class="py-1">
                <v-col cols="5" class="text-caption" style="color:#26C6DA">SMA 200</v-col>
                <v-col cols="7" class="text-caption text-right">{{ fmtPrice(sma200Last) }}</v-col>
              </v-row>
              <v-row no-gutters class="py-1">
                <v-col cols="5" class="text-caption" style="color:#E91E63">EMA 50</v-col>
                <v-col cols="7" class="text-caption text-right">{{ fmtPrice(ema50Last) }}</v-col>
              </v-row>
              <v-row no-gutters class="py-1">
                <v-col cols="5" class="text-caption" style="color:#FF7043">EMA 100</v-col>
                <v-col cols="7" class="text-caption text-right">{{ fmtPrice(ema100Last) }}</v-col>
              </v-row>
              <v-row no-gutters class="py-1">
                <v-col cols="5" class="text-caption" style="color:#66BB6A">EMA 150</v-col>
                <v-col cols="7" class="text-caption text-right">{{ fmtPrice(ema150Last) }}</v-col>
              </v-row>
              <v-row no-gutters class="py-1">
                <v-col cols="5" class="text-caption" style="color:#9C27B0">EMA 200</v-col>
                <v-col cols="7" class="text-caption text-right">{{ fmtPrice(ema200Last) }}</v-col>
              </v-row>

            </v-card-text>
          </v-card>
        </v-col>

        <!-- Right: dominant chart -->
        <v-col cols="12" md="8">
          <StockChart
            :ohlcv="stock.ohlcv"

            :sma50="stock.sma_50"
            :sma200="stock.sma_200"
            :ema50="stock.ema_50"
            :ema100="stock.ema_100"
            :ema150="stock.ema_150"
            :ema200="stock.ema_200"
            :fibonacci="stock.fibonacci"
            :trend-lines="stock.trend_lines"
            :news="news"
            :period="currentPeriod"
            :interval="currentInterval"
            :loading-more="isExpandingHistory"
            @fetch-data="onFetchData"
            @load-more="handleLoadMore"
          />
        </v-col>
      </v-row>

      <!-- ── Row 2: Signals + Trade Setup (left) · News (right) ────────────── -->
      <v-row class="mb-4">
        <v-col cols="12" md="4">
          <Signals
            v-if="signals"
            :buy="signals.buy"
            :sell="signals.sell"
            :hold="signals.hold"
            :breakdown="signals.breakdown"
          />

          <!-- Trade Setup — Fibonacci-based entry/exit calculator -->
          <v-card rounded="lg" class="mt-4">
            <v-card-title class="text-body-1 font-weight-medium pa-4 pb-2">
              <v-icon size="18" class="mr-2">mdi-target</v-icon>
              Trade Setup
            </v-card-title>
            <v-card-text class="pa-4 pt-0">

              <!-- Custom entry price input (optional) -->
              <v-text-field
                v-model="entryInput"
                label="My Entry Price (optional)"
                type="number"
                density="compact"
                variant="outlined"
                hide-details
                clearable
                class="mb-4"
                :placeholder="stock ? String(stock.current_price?.toFixed(2) ?? '') : ''"
              />

              <!-- Suggested best entry from Fibonacci support -->
              <v-row no-gutters align="center" class="mb-3">
                <v-col>
                  <span class="text-body-2">Best Entry</span>
                  <div class="text-caption text-medium-emphasis">
                    {{ suggestedEntry ? `${suggestedEntry.pct}% Fib support` : 'current price' }}
                  </div>
                </v-col>
                <v-col cols="auto">
                  <span class="text-body-2 font-weight-bold">
                    {{ stock ? fmtPrice(suggestedEntry ? suggestedEntry.price : stock.current_price) : '—' }}
                  </span>
                </v-col>
              </v-row>

              <v-divider class="mb-3" />

              <!-- Stop Loss -->
              <v-row v-if="stopLoss" no-gutters align="center" class="mb-2">
                <v-col>
                  <span class="text-body-2">Stop Loss</span>
                  <div class="text-caption text-medium-emphasis">{{ stopLoss.pct }}% Fib</div>
                </v-col>
                <v-col cols="auto" class="text-right">
                  <div class="text-error font-weight-bold text-body-2">{{ fmtPrice(stopLoss.price) }}</div>
                  <div class="text-caption text-error">{{ pctFrom(effectiveEntry, stopLoss.price) }}</div>
                </v-col>
              </v-row>

              <!-- Target 1 — conservative -->
              <v-row v-if="target1" no-gutters align="center" class="mb-2">
                <v-col>
                  <span class="text-body-2">Target 1</span>
                  <div class="text-caption text-medium-emphasis">{{ target1.pct }}% Fib · conservative</div>
                </v-col>
                <v-col cols="auto" class="text-right">
                  <div class="text-success font-weight-bold text-body-2">{{ fmtPrice(target1.price) }}</div>
                  <div class="text-caption text-success">{{ pctFrom(effectiveEntry, target1.price) }}</div>
                </v-col>
              </v-row>

              <!-- Target 2 — aggressive -->
              <v-row v-if="target2" no-gutters align="center" class="mb-3">
                <v-col>
                  <span class="text-body-2">Target 2</span>
                  <div class="text-caption text-medium-emphasis">{{ target2.pct }}% Fib · aggressive</div>
                </v-col>
                <v-col cols="auto" class="text-right">
                  <div class="text-success font-weight-bold text-body-2">{{ fmtPrice(target2.price) }}</div>
                  <div class="text-caption text-success">{{ pctFrom(effectiveEntry, target2.price) }}</div>
                </v-col>
              </v-row>

              <!-- Risk / Reward ratio -->
              <template v-if="riskReward">
                <v-divider class="mb-3" />
                <v-row no-gutters align="center">
                  <v-col class="text-body-2 text-medium-emphasis">Risk / Reward</v-col>
                  <v-col cols="auto">
                    <v-chip
                      size="small"
                      variant="tonal"
                      :color="parseFloat(riskReward) >= 2 ? 'success' : parseFloat(riskReward) >= 1 ? 'warning' : 'error'"
                    >1 : {{ riskReward }}</v-chip>
                  </v-col>
                </v-row>
              </template>

            </v-card-text>
          </v-card>
        </v-col>
        <v-col cols="12" md="8">
          <v-card rounded="lg">
            <v-card-title class="text-body-1 font-weight-medium pa-4 pb-2">
              <v-icon size="18" class="mr-2">mdi-newspaper-variant-outline</v-icon>
              Latest News
            </v-card-title>
            <v-card-text class="pa-3 pt-0">
              <NewsCard
                v-for="item in news"
                :key="item.published_at + item.title"
                :title="item.title"
                :publisher="item.publisher"
                :url="item.url"
                :published-at="item.published_at"
                :sentiment="item.sentiment"
                :compound-score="item.compound_score"
                :related-tickers="item.related_tickers"
              />
              <p v-if="!news.length" class="text-body-2 text-medium-emphasis pa-2">No news available.</p>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>

      <!-- ── ETF Holdings (only shown when is_etf) ───────────────────────────── -->
      <v-row v-if="stock.is_etf" class="mb-4">
        <v-col cols="12">
          <v-card rounded="lg">
            <v-card-title class="text-body-1 font-weight-medium pa-4 pb-2 d-flex align-center flex-wrap ga-2">
              <v-icon size="18" class="mr-2">mdi-format-list-bulleted</v-icon>
              ETF Holdings
              <v-chip size="x-small" variant="tonal" color="primary">
                {{ stock.etf_holdings.length }} holdings
              </v-chip>
              <v-spacer />
              <v-btn
                size="x-small"
                variant="tonal"
                color="secondary"
                :href="`https://etfdb.com/etf/${stock.ticker}/#holdings`"
                target="_blank"
                prepend-icon="mdi-open-in-new"
              >ETFdb</v-btn>
              <v-btn
                size="x-small"
                variant="tonal"
                color="secondary"
                :href="`https://finance.yahoo.com/quote/${stock.ticker}/holdings`"
                target="_blank"
                prepend-icon="mdi-open-in-new"
              >Yahoo Finance</v-btn>
            </v-card-title>
            <v-data-table
              :items="stock.etf_holdings.map((h, i) => ({ ...h, rank: i + 1 }))"
              :headers="etfHoldingsHeaders"
              density="compact"
              :items-per-page="25"
            >
              <template #item.symbol="{ item }">
                <v-btn
                  v-if="item.symbol"
                  variant="text"
                  size="small"
                  color="primary"
                  class="font-weight-bold pa-0"
                  @click="searchStock(item.symbol)"
                >{{ item.symbol }}</v-btn>
                <span v-else class="text-medium-emphasis">—</span>
              </template>
              <template #item.name="{ item }">
                <span class="text-body-2">{{ item.name || '—' }}</span>
              </template>
              <template #item.weight="{ item }">
                <span v-if="item.weight != null">
                  <v-progress-linear
                    :model-value="item.weight"
                    :max="stock.etf_holdings[0]?.weight || 100"
                    rounded
                    height="4"
                    color="primary"
                    bg-color="rgba(255,255,255,0.08)"
                    class="d-inline-flex"
                    style="width:60px; vertical-align:middle"
                  />
                  <span class="text-body-2 ml-2">{{ item.weight.toFixed(2) }}%</span>
                </span>
                <span v-else class="text-medium-emphasis">—</span>
              </template>
              <template #no-data>
                <p class="text-body-2 text-medium-emphasis pa-4">No holdings data available.</p>
              </template>
            </v-data-table>
          </v-card>
        </v-col>
      </v-row>

      <!-- ── Row 3: Fibonacci + Institutional Holders ───────────────────────── -->
      <v-row>
        <v-col cols="12" sm="5" md="3">
          <v-card rounded="lg">
            <v-card-title class="text-body-1 font-weight-medium pa-4 pb-2">
              <v-icon size="18" class="mr-2">mdi-approximately-equal</v-icon>
              Fibonacci (60-day)
            </v-card-title>
            <v-card-text class="pa-0">
              <v-list density="compact" lines="one">
                <v-list-item
                  v-for="(val, key) in stock.fibonacci.levels"
                  :key="key"
                >
                  <template #prepend>
                    <v-chip size="x-small" variant="outlined" class="mr-2" label>{{ key }}%</v-chip>
                  </template>
                  <v-list-item-title class="text-body-2">{{ fmtPrice(val) }}</v-list-item-title>
                </v-list-item>
              </v-list>
            </v-card-text>
          </v-card>
        </v-col>

        <v-col cols="12" sm="7" md="9">
          <v-card rounded="lg">
            <v-card-title class="text-body-1 font-weight-medium pa-4 pb-2">
              <v-icon size="18" class="mr-2">mdi-bank-outline</v-icon>
              Institutional Holders
            </v-card-title>
            <v-data-table
              :items="stock.institutional_holders"
              :headers="holdersHeaders"
              density="compact"
              :items-per-page="10"
            >
              <template #item.shares="{ item }">
                {{ item.shares ? item.shares.toLocaleString() : '—' }}
              </template>
              <template #item.pct_out="{ item }">
                {{ item.pct_out != null ? (item.pct_out * 100).toFixed(2) + '%' : '—' }}
              </template>
              <template #item.value="{ item }">
                {{ item.value ? fmtCap(item.value) : '—' }}
              </template>
            </v-data-table>
          </v-card>
        </v-col>
      </v-row>

    </template>

    <!-- Toast for period/interval errors — old chart stays visible -->
    <v-snackbar v-model="toast" color="error" timeout="4000" location="bottom right">
      <v-icon start>mdi-alert-circle-outline</v-icon>
      {{ toastMsg }}
      <template #actions>
        <v-btn variant="text" @click="toast = false">Dismiss</v-btn>
      </template>
    </v-snackbar>

  </v-container>
</template>
