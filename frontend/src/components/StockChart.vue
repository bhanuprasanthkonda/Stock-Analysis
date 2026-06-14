<script setup>
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { createChart, ColorType, CrosshairMode, LineStyle } from 'lightweight-charts'

const props = defineProps({
  ohlcv:     { type: Array,  default: () => [] },
  sma50:  { type: Array, default: () => [] },
  sma200: { type: Array, default: () => [] },
  ema50:  { type: Array, default: () => [] },
  ema100: { type: Array, default: () => [] },
  ema150: { type: Array, default: () => [] },
  ema200: { type: Array, default: () => [] },
  fibonacci:   { type: Object, default: null },
  trendLines:  { type: Object, default: null },
  news:        { type: Array,  default: () => [] },
  // Controlled from parent so highlight survives re-mounts
  period:      { type: String,  default: '1y' },
  interval:    { type: String,  default: '1d' },
  loadingMore: { type: Boolean, default: false },  // true while parent is fetching more history
})

const emit = defineEmits(['fetch-data', 'load-more'])

// ── Period + interval config ──────────────────────────────────────────────────
const PERIODS = [
  { key: '1d', label: '1D' }, { key: '1w', label: '1W' },
  { key: '1mo', label: '1M' }, { key: '3mo', label: '3M' },
  { key: '6mo', label: '6M' }, { key: 'ytd', label: 'YTD' },
  { key: '1y', label: '1Y' }, { key: '2y', label: '2Y' },
  { key: '5y', label: '5Y' }, { key: 'max', label: 'MAX' },
]

const INTERVALS = [
  { key: '1m',  label: '1m' }, { key: '5m',  label: '5m' },
  { key: '15m', label: '15m' }, { key: '30m', label: '30m' },
  { key: '1h',  label: '1h' }, { key: '1d',  label: '1D' },
  { key: '1wk', label: '1W' },
]

// Default candle interval for each period
const DEFAULT_INTERVAL = {
  '1d': '5m', '1w': '1h', '1mo': '1d', '3mo': '1d',
  '6mo': '1d', 'ytd': '1d', '1y': '1d', '2y': '1d',
  '5y': '1d', 'max': '1wk',
}

// Set before any user-initiated period/interval change so the ohlcv watcher
// knows to call fitContent (show the full new range) instead of preserving scroll.
let _userChangedPeriod = false

// Emit fetch-data with the default interval for the chosen period, so the
// backend returns appropriately sized candles (e.g. 1D → 5m, 1Y → 1d).
function onPeriodSelect(p) {
  _userChangedPeriod = true
  emit('fetch-data', { period: p, interval: DEFAULT_INTERVAL[p] ?? '1d' })
}

// Emit fetch-data keeping the current period — only the candle size changes.
function onIntervalSelect(i) {
  _userChangedPeriod = true
  emit('fetch-data', { period: props.period, interval: i })
}

// ── Overlay toggles ───────────────────────────────────────────────────────────
const showSMA50  = ref(true)
const showSMA200 = ref(true)
const showEMA50  = ref(false)
const showEMA100 = ref(false)
const showEMA150 = ref(false)
const showEMA200 = ref(false)
const showFib       = ref(true)
const showNews      = ref(true)
const showVolume    = ref(true)
const showTrendUp   = ref(true)
const showTrendDown = ref(true)

// ── News hover tooltip ────────────────────────────────────────────────────────
// Filled by the crosshair-move handler; cleared when cursor leaves a news date.
const hoveredNews = ref([])

// ── Chart DOM ref + mutable chart objects ─────────────────────────────────────
const chartEl = ref(null)
let chart     = null
let candleS   = null
let volS      = null
let sma50S  = null
let sma200S = null
let ema50S  = null
let ema100S = null
let ema150S = null
let ema200S = null
let fibLines        = []
let trendUpS        = null
let trendDownS      = null
let resizeObs       = null
let _loadMoreEmitted = false  // prevents duplicate emit before parent sets loadingMore=true

// ── Data builders ─────────────────────────────────────────────────────────────

// Map OHLCV records to the shape lightweight-charts expects for candlestick series.
const buildCandles = () =>
  props.ohlcv.map(c => ({ time: c.date, open: c.open, high: c.high, low: c.low, close: c.close }))

// Map a SMA/EMA array (may contain leading nulls) to {time, value} pairs, skipping nulls.
// Indexes align with ohlcv so c.date is the correct timestamp for arr[i].
const buildLine = arr =>
  props.ohlcv
    .map((c, i) => arr?.[i] != null ? { time: c.date, value: arr[i] } : null)
    .filter(Boolean)

// Build volume histogram bars. Color is green-tinted for up-candles, red-tinted for down.
const buildVolumes = () =>
  props.ohlcv.map(c => ({
    time: c.date,
    value: c.volume,
    color: c.close >= c.open ? 'rgba(38,166,154,0.35)' : 'rgba(239,83,80,0.35)',
  }))

// ── Fibonacci price lines ─────────────────────────────────────────────────────
const FIB_COLORS = {
  '0': '#9E9E9E', '23.6': '#FF9800', '38.2': '#2196F3',
  '50.0': '#E91E63', '61.8': '#4CAF50', '78.6': '#9C27B0', '100': '#9E9E9E',
}

// Clear existing Fibonacci price lines then redraw them on the candlestick series.
// Price lines must be removed before re-adding — there is no "update" API in lightweight-charts.
function applyFib() {
  if (!candleS) return
  fibLines.forEach(l => candleS.removePriceLine(l))
  fibLines = []
  if (!showFib.value || !props.fibonacci?.levels) return
  Object.entries(props.fibonacci.levels).forEach(([key, val]) => {
    fibLines.push(candleS.createPriceLine({
      price: val,
      color: FIB_COLORS[key] ?? '#9e9e9e',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: `${key}%`,
    }))
  })
}

// ── Trend lines ───────────────────────────────────────────────────────────────

// Push uptrend and downtrend line data into their series. Each trend line is
// 3 points: two pivot anchors + a projected end at the last candle's timestamp.
function applyTrends() {
  if (!trendUpS || !trendDownS) return
  const up = props.trendLines?.uptrend
  const dn = props.trendLines?.downtrend
  trendUpS.setData(showTrendUp.value && up
    ? up.map(p => ({ time: p.date, value: p.price })) : [])
  trendDownS.setData(showTrendDown.value && dn
    ? dn.map(p => ({ time: p.date, value: p.price })) : [])
}

// ── News markers ──────────────────────────────────────────────────────────────

// Convert a Unix timestamp (seconds) to a UTC calendar date string "YYYY-MM-DD".
// Used to match news publication dates against OHLCV candle dates (which are also UTC).
function tsToUTCDate(unix) {
  const d = new Date(unix * 1000)
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`
}

// Place one marker per calendar day, keeping only the highest-magnitude article.
// This prevents stacking when multiple articles land on the same date.
// Markers are sorted by time because lightweight-charts requires ascending order.
function applyNewsMarkers() {
  if (!candleS) return
  if (!showNews.value || !props.news?.length) { candleS.setMarkers([]); return }

  const byDate = {}
  props.news.filter(n => n.published_at).forEach(n => {
    const d = n.published_at.slice(0, 10)
    if (!byDate[d] || Math.abs(n.compound_score) > Math.abs(byDate[d].compound_score)) byDate[d] = n
  })

  const markers = []
  Object.entries(byDate).forEach(([d, n]) => {
    const candle = props.ohlcv.find(c => tsToUTCDate(c.date) === d)
    if (!candle) return
    markers.push({
      time: candle.date,
      position: 'aboveBar',
      color: n.sentiment === 'good' ? '#4CAF50' : n.sentiment === 'bad' ? '#EF5350' : '#757575',
      shape: n.sentiment === 'good' ? 'arrowUp' : n.sentiment === 'bad' ? 'arrowDown' : 'circle',
      size: 1,
    })
  })

  candleS.setMarkers(markers.sort((a, b) => a.time - b.time))
}

// ── Chart init ────────────────────────────────────────────────────────────────

// Create the lightweight-charts instance, add all series in the right layer order
// (volume histogram first so it renders behind candles), then call refreshAll().
// A ResizeObserver keeps the chart width synced with its container.
function initChart() {
  chart = createChart(chartEl.value, {
    width: chartEl.value.clientWidth,
    height: 540,
    layout: {
      background: { type: ColorType.Solid, color: 'transparent' },
      textColor: '#9e9e9e',
    },
    grid: {
      vertLines: { color: 'rgba(255,255,255,0.05)' },
      horzLines: { color: 'rgba(255,255,255,0.05)' },
    },
    crosshair: { mode: CrosshairMode.Normal },
    rightPriceScale: {
      borderColor: 'rgba(255,255,255,0.1)',
      scaleMargins: { top: 0.05, bottom: 0.22 },
    },
    timeScale: {
      borderColor: 'rgba(255,255,255,0.1)',
      timeVisible: true,
      secondsVisible: false,
    },
    handleScroll: true,
    handleScale: true,
  })

  volS = chart.addHistogramSeries({
    priceScaleId: '',
    priceFormat: { type: 'volume' },
    color: 'rgba(69,90,100,0.35)',
  })
  chart.priceScale('').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } })

  candleS = chart.addCandlestickSeries({
    upColor: '#26a69a',
    downColor: '#ef5350',
    borderVisible: false,
    wickUpColor: '#26a69a',
    wickDownColor: '#ef5350',
  })

  const lineOpts = { lineWidth: 2, lastValueVisible: false, priceLineVisible: false }
  sma50S  = chart.addLineSeries({ ...lineOpts, color: '#FF9800' })
  sma200S = chart.addLineSeries({ ...lineOpts, color: '#26C6DA' })
  ema50S  = chart.addLineSeries({ ...lineOpts, color: '#E91E63' })
  ema100S = chart.addLineSeries({ ...lineOpts, color: '#FF7043' })
  ema150S = chart.addLineSeries({ ...lineOpts, color: '#66BB6A' })
  ema200S = chart.addLineSeries({ ...lineOpts, color: '#9C27B0' })

  // Trend lines: dashed, no crosshair dot, drawn on the same price scale as candles.
  const trendOpts = { ...lineOpts, lineWidth: 2, lineStyle: LineStyle.Dashed, crosshairMarkerVisible: false }
  trendUpS   = chart.addLineSeries({ ...trendOpts, color: '#26A69A' })
  trendDownS = chart.addLineSeries({ ...trendOpts, color: '#EF5350' })

  // Emit load-more when the user pans left to within 10 bars of the dataset start.
  // _loadMoreEmitted (module-level) prevents duplicate emits in the brief gap before
  // the parent sets loadingMore=true. It's reset in the loadingMore watch below.
  chart.timeScale().subscribeVisibleLogicalRangeChange(range => {
    if (!range || props.loadingMore || _loadMoreEmitted) return
    if (range.from < 10) {
      _loadMoreEmitted = true
      emit('load-more')
    }
  })

  // When the crosshair moves to a date that has news markers, populate hoveredNews
  // so the tooltip overlay renders. param.time is a Unix int for our data format.
  chart.subscribeCrosshairMove(param => {
    if (!param.time || !showNews.value || !props.news?.length) {
      hoveredNews.value = []
      return
    }
    const d = tsToUTCDate(typeof param.time === 'number' ? param.time : Number(param.time))
    hoveredNews.value = props.news.filter(n => n.published_at?.startsWith(d))
  })

  refreshAll()

  resizeObs = new ResizeObserver(() => {
    if (chartEl.value && chart) chart.applyOptions({ width: chartEl.value.clientWidth })
  })
  resizeObs.observe(chartEl.value)
}

// Push fresh data into every series. `fit=true` zooms to show all bars (used
// after a period change); `fit=false` preserves the current pan position (used
// when more historical data is prepended during infinite-scroll expansion).
function refreshAll(fit = true) {
  if (!chart) return
  candleS.setData(buildCandles())
  volS.setData(showVolume.value    ? buildVolumes()          : [])
  sma50S.setData(showSMA50.value   ? buildLine(props.sma50)  : [])
  sma200S.setData(showSMA200.value ? buildLine(props.sma200) : [])
  ema50S.setData(showEMA50.value   ? buildLine(props.ema50)  : [])
  ema100S.setData(showEMA100.value ? buildLine(props.ema100) : [])
  ema150S.setData(showEMA150.value ? buildLine(props.ema150) : [])
  ema200S.setData(showEMA200.value ? buildLine(props.ema200) : [])
  applyFib()
  applyTrends()
  applyNewsMarkers()
  if (fit) chart.timeScale().fitContent()
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────

// Init on mount only if data is already available (e.g. navigating back with cache).
onMounted(() => {
  if (props.ohlcv.length) initChart()
})

// Re-init (first load), refresh + fit (period/interval change), or
// refresh + shift (history expansion) when OHLCV data arrives.
// nextTick ensures the DOM container is rendered before lightweight-charts measures it.
watch(() => props.ohlcv, async (newVal, oldVal) => {
  if (!newVal.length) return
  await nextTick()
  if (!chart) { initChart(); _userChangedPeriod = false; return }

  // Detect history expansion: same right-edge timestamp, more bars on the left,
  // and the change was NOT triggered by the user clicking a period/interval button.
  const oldLast = oldVal?.length ? oldVal[oldVal.length - 1]?.date : null
  const newLast = newVal[newVal.length - 1]?.date
  const isExpand = !_userChangedPeriod && oldLast && oldLast === newLast && newVal.length > oldVal.length

  if (isExpand) {
    // Preserve the current scroll position by shifting the logical range
    // rightward by the number of bars that were prepended to the left.
    const range = chart.timeScale().getVisibleLogicalRange()
    const added = newVal.length - oldVal.length
    refreshAll(false)
    if (range) {
      chart.timeScale().setVisibleLogicalRange({
        from: range.from + added,
        to: range.to + added,
      })
    }
  } else {
    refreshAll()
  }

  _userChangedPeriod = false
})

// Fibonacci, trend lines, and news come from separate backend calls — watch independently.
watch(() => props.fibonacci,   applyFib)
watch(() => props.trendLines,  applyTrends)
watch(() => props.news,        applyNewsMarkers)

// Reset the emit guard when the parent finishes loading so the NEXT left-edge pan
// can trigger another expansion round.
watch(() => props.loadingMore, v => { if (!v) _loadMoreEmitted = false })

// Toggle watches: each one flips a single series on/off without a full redraw.
watch(showFib,       applyFib)
watch(showTrendUp,   applyTrends)
watch(showTrendDown, applyTrends)
watch(showNews, v => { applyNewsMarkers(); if (!v) hoveredNews.value = [] })
watch(showSMA50,  v => sma50S?.setData(v  ? buildLine(props.sma50)  : []))
watch(showSMA200, v => sma200S?.setData(v ? buildLine(props.sma200) : []))
watch(showEMA50,  v => ema50S?.setData(v  ? buildLine(props.ema50)  : []))
watch(showEMA100, v => ema100S?.setData(v ? buildLine(props.ema100) : []))
watch(showEMA150, v => ema150S?.setData(v ? buildLine(props.ema150) : []))
watch(showEMA200, v => ema200S?.setData(v ? buildLine(props.ema200) : []))
watch(showVolume, v => volS?.setData(v     ? buildVolumes()           : []))

// Disconnect the resize observer and destroy the chart to release WebGL resources.
onBeforeUnmount(() => {
  resizeObs?.disconnect()
  chart?.remove()
  chart = null
})
</script>

<template>
  <v-card rounded="lg">
    <v-card-title class="pa-3 pb-1">

      <!-- Row 1: title + overlay toggles -->
      <v-row align="center" no-gutters class="mb-1">
        <v-col cols="auto" class="text-body-1 font-weight-medium mr-3 d-flex align-center ga-2">
          <v-icon size="18">mdi-candlestick</v-icon>
          Price Chart
          <v-chip v-if="loadingMore" size="x-small" color="primary" variant="tonal">
            <v-progress-circular size="10" width="2" indeterminate class="mr-1" />
            Loading history…
          </v-chip>
        </v-col>
        <v-col>
          <div class="d-flex flex-wrap ga-1">
            <v-chip size="small" :color="showSMA50  ? '#FF9800' : 'grey'" :variant="showSMA50  ? 'flat' : 'text'" @click="showSMA50  = !showSMA50">SMA 50</v-chip>
            <v-chip size="small" :color="showSMA200 ? '#26C6DA' : 'grey'" :variant="showSMA200 ? 'flat' : 'text'" @click="showSMA200 = !showSMA200">SMA 200</v-chip>
            <v-chip size="small" :color="showEMA50  ? '#E91E63' : 'grey'" :variant="showEMA50  ? 'flat' : 'text'" @click="showEMA50  = !showEMA50">EMA 50</v-chip>
            <v-chip size="small" :color="showEMA100 ? '#FF7043' : 'grey'" :variant="showEMA100 ? 'flat' : 'text'" @click="showEMA100 = !showEMA100">EMA 100</v-chip>
            <v-chip size="small" :color="showEMA150 ? '#66BB6A' : 'grey'" :variant="showEMA150 ? 'flat' : 'text'" @click="showEMA150 = !showEMA150">EMA 150</v-chip>
            <v-chip size="small" :color="showEMA200 ? '#9C27B0' : 'grey'" :variant="showEMA200 ? 'flat' : 'text'" @click="showEMA200 = !showEMA200">EMA 200</v-chip>
            <v-chip size="small" :color="showFib       ? '#FFA726' : 'grey'" :variant="showFib       ? 'flat' : 'text'" @click="showFib       = !showFib">Fib</v-chip>
            <v-chip size="small" :color="showTrendUp   ? '#26A69A' : 'grey'" :variant="showTrendUp   ? 'flat' : 'text'" @click="showTrendUp   = !showTrendUp">↑ Trend</v-chip>
            <v-chip size="small" :color="showTrendDown ? '#EF5350' : 'grey'" :variant="showTrendDown ? 'flat' : 'text'" @click="showTrendDown = !showTrendDown">↓ Trend</v-chip>
            <v-chip size="small" :color="showNews      ? '#4CAF50' : 'grey'" :variant="showNews      ? 'flat' : 'text'" @click="showNews      = !showNews">News</v-chip>
            <v-chip size="small" :color="showVolume    ? '#546E7A' : 'grey'" :variant="showVolume    ? 'flat' : 'text'" @click="showVolume    = !showVolume">Vol</v-chip>
          </div>
        </v-col>
      </v-row>

      <!-- Row 2: period selector + interval selector -->
      <v-row align="center" no-gutters>
        <v-col cols="auto">
          <v-btn-toggle
            :model-value="period"
            density="compact"
            color="primary"
            variant="text"
            mandatory
            @update:model-value="onPeriodSelect"
          >
            <v-btn v-for="p in PERIODS" :key="p.key" :value="p.key" size="x-small">{{ p.label }}</v-btn>
          </v-btn-toggle>
        </v-col>

        <v-divider vertical class="mx-3" />

        <v-col cols="auto" class="d-flex align-center">
          <span class="text-caption text-medium-emphasis mr-2">Candle</span>
          <v-btn-toggle
            :model-value="interval"
            density="compact"
            color="secondary"
            variant="text"
            mandatory
            @update:model-value="onIntervalSelect"
          >
            <v-btn v-for="i in INTERVALS" :key="i.key" :value="i.key" size="x-small">{{ i.label }}</v-btn>
          </v-btn-toggle>
        </v-col>
      </v-row>

    </v-card-title>

    <v-card-text class="pa-0" :style="{ position: 'relative' }">
      <!-- Empty state -->
      <v-row v-if="!ohlcv.length" justify="center" align="center" style="height:540px">
        <v-col class="text-center">
          <v-icon size="48" color="surface-variant">mdi-candlestick</v-icon>
          <p class="text-body-2 text-medium-emphasis mt-2">Search a ticker to load chart data</p>
        </v-col>
      </v-row>

      <!-- News hover tooltip — appears when the crosshair lands on a news-marker date -->
      <v-card
        v-if="hoveredNews.length && showNews"
        elevation="8"
        rounded="lg"
        :style="{ position: 'absolute', top: '8px', left: '8px', zIndex: 10, maxWidth: '360px', pointerEvents: 'none' }"
        class="pa-3"
      >
        <div class="d-flex align-center ga-1 mb-2">
          <v-icon size="14" color="primary">mdi-newspaper-variant-outline</v-icon>
          <span class="text-caption font-weight-medium text-primary">
            {{ hoveredNews[0].published_at.slice(0, 10) }}
          </span>
        </div>
        <div
          v-for="n in hoveredNews.slice(0, 4)"
          :key="n.title"
          class="d-flex align-start ga-2 mb-2"
        >
          <v-chip
            size="x-small"
            :color="n.sentiment === 'good' ? 'success' : n.sentiment === 'bad' ? 'error' : 'default'"
            variant="tonal"
            class="flex-shrink-0 mt-1"
          >{{ n.sentiment }}</v-chip>
          <span class="text-body-2">{{ n.title }}</span>
        </div>
      </v-card>

      <!-- Chart container -->
      <div v-show="ohlcv.length" ref="chartEl" />
    </v-card-text>
  </v-card>
</template>
