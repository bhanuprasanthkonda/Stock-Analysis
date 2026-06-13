<script setup>
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { createChart, ColorType, CrosshairMode, LineStyle } from 'lightweight-charts'

const props = defineProps({
  ohlcv:     { type: Array,  default: () => [] },
  sma20:     { type: Array,  default: () => [] },
  sma50:     { type: Array,  default: () => [] },
  sma200:    { type: Array,  default: () => [] },
  ema20:     { type: Array,  default: () => [] },
  ema50:     { type: Array,  default: () => [] },
  fibonacci: { type: Object, default: null },
  news:      { type: Array,  default: () => [] },
  // Controlled from parent so highlight survives re-mounts
  period:   { type: String, default: '1y' },
  interval: { type: String, default: '1d' },
})

const emit = defineEmits(['fetch-data'])

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

function onPeriodSelect(p) {
  emit('fetch-data', { period: p, interval: DEFAULT_INTERVAL[p] ?? '1d' })
}

function onIntervalSelect(i) {
  emit('fetch-data', { period: props.period, interval: i })
}

// ── Overlay toggles ───────────────────────────────────────────────────────────
const showSMA20  = ref(true)
const showSMA50  = ref(true)
const showSMA200 = ref(false)
const showEMA20  = ref(false)
const showEMA50  = ref(false)
const showFib    = ref(true)
const showNews   = ref(true)
const showVolume = ref(true)

// ── Chart DOM ref + mutable chart objects ─────────────────────────────────────
const chartEl = ref(null)
let chart     = null
let candleS   = null
let volS      = null
let sma20S    = null
let sma50S    = null
let sma200S   = null
let ema20S    = null
let ema50S    = null
let fibLines  = []
let resizeObs = null

// ── Data builders ─────────────────────────────────────────────────────────────
const buildCandles = () =>
  props.ohlcv.map(c => ({ time: c.date, open: c.open, high: c.high, low: c.low, close: c.close }))

const buildLine = arr =>
  props.ohlcv
    .map((c, i) => arr?.[i] != null ? { time: c.date, value: arr[i] } : null)
    .filter(Boolean)

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

// ── News markers ──────────────────────────────────────────────────────────────
function tsToUTCDate(unix) {
  const d = new Date(unix * 1000)
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`
}

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
  sma20S  = chart.addLineSeries({ ...lineOpts, color: '#2196F3' })
  sma50S  = chart.addLineSeries({ ...lineOpts, color: '#FF9800' })
  sma200S = chart.addLineSeries({ ...lineOpts, color: '#26C6DA' })
  ema20S  = chart.addLineSeries({ ...lineOpts, color: '#9C27B0' })
  ema50S  = chart.addLineSeries({ ...lineOpts, color: '#E91E63' })

  refreshAll()

  resizeObs = new ResizeObserver(() => {
    if (chartEl.value && chart) chart.applyOptions({ width: chartEl.value.clientWidth })
  })
  resizeObs.observe(chartEl.value)
}

function refreshAll() {
  if (!chart) return
  candleS.setData(buildCandles())
  volS.setData(showVolume.value    ? buildVolumes()          : [])
  sma20S.setData(showSMA20.value   ? buildLine(props.sma20)  : [])
  sma50S.setData(showSMA50.value   ? buildLine(props.sma50)  : [])
  sma200S.setData(showSMA200.value ? buildLine(props.sma200) : [])
  ema20S.setData(showEMA20.value   ? buildLine(props.ema20)  : [])
  ema50S.setData(showEMA50.value   ? buildLine(props.ema50)  : [])
  applyFib()
  applyNewsMarkers()
  chart.timeScale().fitContent()
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────
onMounted(() => {
  if (props.ohlcv.length) initChart()
})

watch(() => props.ohlcv, async val => {
  if (!val.length) return
  await nextTick()
  if (!chart) initChart()
  else refreshAll()
})

watch(() => props.fibonacci, applyFib)
watch(() => props.news, applyNewsMarkers)

watch(showFib,    applyFib)
watch(showNews,   applyNewsMarkers)
watch(showSMA20,  v => sma20S?.setData(v   ? buildLine(props.sma20)  : []))
watch(showSMA50,  v => sma50S?.setData(v   ? buildLine(props.sma50)  : []))
watch(showSMA200, v => sma200S?.setData(v  ? buildLine(props.sma200) : []))
watch(showEMA20,  v => ema20S?.setData(v   ? buildLine(props.ema20)  : []))
watch(showEMA50,  v => ema50S?.setData(v   ? buildLine(props.ema50)  : []))
watch(showVolume, v => volS?.setData(v     ? buildVolumes()           : []))

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
        <v-col cols="auto" class="text-body-1 font-weight-medium mr-3">
          <v-icon size="18" class="mr-1">mdi-candlestick</v-icon>
          Price Chart
        </v-col>
        <v-col>
          <div class="d-flex flex-wrap ga-1">
            <v-chip size="small" :color="showSMA20  ? '#2196F3' : 'grey'" :variant="showSMA20  ? 'flat' : 'text'" @click="showSMA20  = !showSMA20">SMA 20</v-chip>
            <v-chip size="small" :color="showSMA50  ? '#FF9800' : 'grey'" :variant="showSMA50  ? 'flat' : 'text'" @click="showSMA50  = !showSMA50">SMA 50</v-chip>
            <v-chip size="small" :color="showSMA200 ? '#26C6DA' : 'grey'" :variant="showSMA200 ? 'flat' : 'text'" @click="showSMA200 = !showSMA200">SMA 200</v-chip>
            <v-chip size="small" :color="showEMA20  ? '#9C27B0' : 'grey'" :variant="showEMA20  ? 'flat' : 'text'" @click="showEMA20  = !showEMA20">EMA 20</v-chip>
            <v-chip size="small" :color="showEMA50  ? '#E91E63' : 'grey'" :variant="showEMA50  ? 'flat' : 'text'" @click="showEMA50  = !showEMA50">EMA 50</v-chip>
            <v-chip size="small" :color="showFib    ? '#FFA726' : 'grey'" :variant="showFib    ? 'flat' : 'text'" @click="showFib    = !showFib">Fib</v-chip>
            <v-chip size="small" :color="showNews   ? '#4CAF50' : 'grey'" :variant="showNews   ? 'flat' : 'text'" @click="showNews   = !showNews">News</v-chip>
            <v-chip size="small" :color="showVolume ? '#546E7A' : 'grey'" :variant="showVolume ? 'flat' : 'text'" @click="showVolume = !showVolume">Vol</v-chip>
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

    <v-card-text class="pa-0">
      <!-- Empty state -->
      <v-row v-if="!ohlcv.length" justify="center" align="center" style="height:540px">
        <v-col class="text-center">
          <v-icon size="48" color="surface-variant">mdi-candlestick</v-icon>
          <p class="text-body-2 text-medium-emphasis mt-2">Search a ticker to load chart data</p>
        </v-col>
      </v-row>

      <!-- Chart container -->
      <div v-show="ohlcv.length" ref="chartEl" />
    </v-card-text>
  </v-card>
</template>
