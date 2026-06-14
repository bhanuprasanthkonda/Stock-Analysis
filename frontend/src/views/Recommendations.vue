<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()

const recs         = ref([])
const loading      = ref(false)
const error        = ref(null)

// ── Market Pulse (indices + futures) ─────────────────────────────────────────
const marketPulse   = ref(null)
const pulseLoading  = ref(false)

async function fetchPulse() {
  pulseLoading.value = true
  try {
    marketPulse.value = (await api.get('/recommendations/market-pulse')).data
  } catch {}
  finally { pulseLoading.value = false }
}

function directionColor(d) {
  return d === 'bullish' ? 'success' : d === 'bearish' ? 'error' : 'warning'
}
function directionLabel(d) {
  return d === 'bullish' ? 'Bullish' : d === 'bearish' ? 'Bearish' : 'Neutral'
}
function directionIcon(d) {
  return d === 'bullish' ? 'mdi-trending-up' : d === 'bearish' ? 'mdi-trending-down' : 'mdi-minus'
}

// ── Search state ──────────────────────────────────────────────────────────────
const searchQuery       = ref(null)   // selected item object (v-model)
const searchText        = ref('')     // raw typed text from @update:search
const searchSuggestions = ref([])
const searchLoading     = ref(false)
const searchResult      = ref(null)
const searchError       = ref(null)
const searchFetching    = ref(false)
const searchHistory     = ref([])

let searchDebounce = null
function onSearchType(text) {
  searchText.value = text || ''
  searchSuggestions.value = []
  if (!text || text.length < 1) return
  clearTimeout(searchDebounce)
  searchDebounce = setTimeout(async () => {
    searchLoading.value = true
    try {
      const res = await api.get(`/stocks/search?q=${encodeURIComponent(text)}`)
      searchSuggestions.value = res.data
    } catch {}
    finally { searchLoading.value = false }
  }, 300)
}

async function doSearch(raw) {
  if (!raw) return
  const ticker = (typeof raw === 'string' ? raw : raw.ticker).trim().toUpperCase()
  if (!ticker) return
  searchResult.value   = null
  searchError.value    = null
  searchFetching.value = true
  try {
    const res = await api.get(`/recommendations/${ticker}`)
    searchResult.value = res.data
  } catch (e) {
    searchError.value = e.response?.data?.detail ?? `Could not fetch data for ${ticker}`
  } finally {
    searchFetching.value = false
  }
}

function onSearchSelect(item) {
  if (item) doSearch(item)
}

function onSearchEnter() {
  // Use the live typed text — searchQuery (v-model) holds the selected object,
  // not the current input string, so it's unreliable here.
  const raw = searchText.value.trim() || (typeof searchQuery.value === 'string' ? searchQuery.value : searchQuery.value?.ticker)
  if (raw) doSearch(raw)
}

function clearSearch() {
  searchQuery.value       = null
  searchText.value        = ''
  searchSuggestions.value = []
  searchResult.value      = null
  searchError.value       = null
}

async function fetchRecs() {
  loading.value = true
  error.value   = null
  try {
    const res  = await api.get('/recommendations/')
    recs.value = res.data
  } catch (e) {
    error.value = 'Failed to load recommendations. Make sure the backend is running.'
    recs.value  = []
  } finally {
    loading.value = false
  }
}

async function fetchHistory() {
  try {
    const res = await api.get('/portfolio/history')
    searchHistory.value = res.data
  } catch {}
}

onMounted(() => { fetchRecs(); fetchHistory(); fetchPulse() })

// ── Formatters ────────────────────────────────────────────────────────────────
const fmtPrice = v => v != null ? '$' + Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 }) : '—'
const fmtChg   = v => v != null ? (v >= 0 ? '+' : '') + v.toFixed(2) : ''
const fmtPct   = v => v != null ? (v >= 0 ? '+' : '') + v.toFixed(2) + '%' : ''
const chgColor = v => v == null ? '' : v >= 0 ? 'text-success' : 'text-error'
const sentimentColor = s => s === 'good' ? 'success' : s === 'bad' ? 'error' : 'warning'

// ── Chip helpers ──────────────────────────────────────────────────────────────
function crossChip(val) {
  if (!val) return null
  return {
    label: val === 'golden' ? 'Golden Cross' : 'Death Cross',
    color: val === 'golden' ? 'success' : 'error',
  }
}

function volChip(val) {
  if (!val || val === 'normal' || val === 'insufficient_data') return null
  return {
    label: val === 'elevated_bullish' ? '↑ Volume' : '↓ Volume',
    color: val === 'elevated_bullish' ? 'success' : 'error',
  }
}

function newsChip(bd) {
  if (!bd) return null
  const good = bd.news_good || 0
  const bad  = bd.news_bad  || 0
  if (good === 0 && bad === 0) return null
  if (good > bad)  return { label: `Positive News (${good})`, color: 'success' }
  if (bad  > good) return { label: `Negative News (${bad})`,  color: 'error'   }
  return { label: 'Mixed News', color: 'warning' }
}

function buyChipColor(pct) {
  return pct >= 65 ? 'success' : 'warning'
}

function openDashboard(ticker) {
  router.push(`/dashboard?ticker=${ticker}`)
}

function fmtDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}
</script>

<template>
  <v-container class="pa-6" max-width="1300">
    <!-- Header -->
    <div class="d-flex align-center mb-6" style="gap:12px">
      <v-icon size="28" color="warning">mdi-lightbulb-outline</v-icon>
      <div>
        <div class="text-h5 font-weight-bold">Recommendations</div>
        <div class="text-caption text-medium-emphasis">
          Buy-signal stocks from your portfolio &amp; watchlists · Updated on load
        </div>
      </div>
      <v-spacer />
      <v-btn variant="tonal" size="small" prepend-icon="mdi-refresh" @click="fetchRecs" :loading="loading">
        Refresh
      </v-btn>
    </div>

    <!-- ── Market Pulse ────────────────────────────────────────────────────── -->
    <v-sheet
      rounded="lg"
      :style="{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)' }"
      class="d-flex align-center px-3 mb-5"
      style="height:44px; overflow-x:auto; gap:0"
    >
      <v-progress-circular v-if="pulseLoading && !marketPulse" indeterminate size="16" width="2" color="primary" class="mx-2" />

      <template v-if="marketPulse">
        <!-- Index items -->
        <template v-for="(idx, i) in marketPulse.indices" :key="idx.ticker">
          <div
            class="d-flex align-center px-3"
            style="gap:6px; cursor:pointer; white-space:nowrap; height:100%"
            @click="openDashboard(idx.ticker)"
          >
            <span class="text-caption text-medium-emphasis">{{ idx.label }}</span>
            <span class="text-body-2 font-weight-bold">
              ${{ Number(idx.price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}
            </span>
            <span :class="idx.chg_pct >= 0 ? 'text-success' : 'text-error'" class="text-caption font-weight-medium">
              {{ idx.chg_pct != null ? (idx.chg_pct >= 0 ? '+' : '') + idx.chg_pct.toFixed(2) + '%' : '' }}
            </span>
            <v-icon size="13" :color="directionColor(idx.direction)">{{ directionIcon(idx.direction) }}</v-icon>
          </div>
          <v-divider vertical class="my-2" />
        </template>

        <!-- Futures items -->
        <template v-for="(fut, i) in marketPulse.futures" :key="fut.ticker">
          <div class="d-flex align-center px-3" style="gap:6px; white-space:nowrap; height:100%">
            <span class="text-caption text-medium-emphasis">{{ fut.label.replace(' Futures', ' Fut') }}</span>
            <span class="text-body-2 font-weight-medium">
              {{ Number(fut.price).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) }}
            </span>
            <span
              :class="fut.chg_pct != null && fut.chg_pct >= 0 ? 'text-success' : 'text-error'"
              class="text-caption font-weight-medium"
            >
              {{ fut.chg_pct != null ? (fut.chg_pct >= 0 ? '+' : '') + fut.chg_pct.toFixed(2) + '%' : '' }}
            </span>
          </div>
          <v-divider v-if="i < marketPulse.futures.length - 1" vertical class="my-2" />
        </template>
      </template>

      <v-spacer />
      <v-btn icon="mdi-refresh" size="x-small" variant="text" :loading="pulseLoading" @click="fetchPulse" class="ml-1" />
    </v-sheet>

    <!-- Search bar -->
    <v-autocomplete
      v-model="searchQuery"
      :items="searchSuggestions"
      item-title="name"
      item-value="ticker"
      :loading="searchLoading"
      placeholder="Search any stock or ETF…"
      prepend-inner-icon="mdi-magnify"
      variant="outlined"
      density="compact"
      rounded="lg"
      clearable
      hide-details
      return-object
      no-filter
      class="mb-2"
      style="max-width: 420px"
      @update:search="onSearchType"
      @update:model-value="onSearchSelect"
      @keydown.enter="onSearchEnter"
      @click:clear="clearSearch"
    >
      <template #item="{ item, props: iProps }">
        <v-list-item v-bind="iProps">
          <template #title>
            <span class="font-weight-bold">{{ item.raw.ticker }}</span>
            <span class="text-medium-emphasis ml-2 text-caption">{{ item.raw.name }}</span>
          </template>
        </v-list-item>
      </template>
    </v-autocomplete>

    <!-- Recent searches -->
    <div v-if="searchHistory.length" class="d-flex align-center flex-wrap ga-2 mb-4">
      <v-icon size="13" color="medium-emphasis">mdi-history</v-icon>
      <span class="text-overline text-medium-emphasis">Recents</span>
      <v-chip
        v-for="h in searchHistory.slice(0, 10)"
        :key="h.ticker"
        size="small"
        variant="tonal"
        color="primary"
        @click="doSearch(h.ticker)"
      >
        <span class="font-weight-medium">{{ h.ticker }}</span>
        <span v-if="h.company_name" class="text-medium-emphasis ml-1 text-caption">· {{ h.company_name }}</span>
      </v-chip>
    </div>

    <!-- Search result card -->
    <v-progress-linear v-if="searchFetching" indeterminate color="primary" class="mb-4" rounded />
    <v-alert v-if="searchError" type="error" variant="tonal" class="mb-4" closable @click:close="searchError = null">
      {{ searchError }}
    </v-alert>
    <template v-if="searchResult && !searchFetching">
      <div class="text-caption text-medium-emphasis mb-2 font-weight-medium" style="letter-spacing:0.08em">
        SEARCH RESULT
      </div>
      <v-row class="mb-4">
        <v-col cols="12" md="6">
          <v-card rounded="lg" border :style="{ borderColor: searchResult.buy_pct >= 50 ? 'rgba(76,175,80,0.4)' : 'rgba(239,83,80,0.3)' }">
            <v-card-title class="pt-4 pb-1 px-4">
              <div class="d-flex align-center" style="gap:10px; flex-wrap:wrap">
                <v-btn variant="tonal" size="small" rounded="lg" color="primary" @click="openDashboard(searchResult.ticker)">
                  {{ searchResult.ticker }}
                </v-btn>
                <span class="text-body-2 text-medium-emphasis flex-grow-1" style="min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">
                  {{ searchResult.company_name || '' }}
                </span>
                <v-chip size="small" :color="buyChipColor(searchResult.buy_pct)" variant="flat" class="font-weight-bold">
                  BUY {{ searchResult.buy_pct.toFixed(0) }}%
                </v-chip>
              </div>
              <div class="d-flex align-center mt-1" style="gap:8px">
                <span class="text-h6 font-weight-bold">{{ fmtPrice(searchResult.current_price) }}</span>
                <span v-if="searchResult.day_change != null" :class="chgColor(searchResult.day_change)" class="text-body-2">
                  {{ fmtChg(searchResult.day_change) }} ({{ fmtPct(searchResult.day_change_pct) }})
                </span>
              </div>
              <div class="d-flex align-center mt-2" style="gap:10px">
                <div class="d-flex align-center flex-grow-1" style="gap:4px">
                  <span class="text-caption text-success font-weight-bold" style="min-width:12px">B</span>
                  <v-progress-linear :model-value="searchResult.buy_pct" color="success" rounded height="5" />
                  <span class="text-caption text-success" style="min-width:28px; text-align:right">{{ searchResult.buy_pct?.toFixed(0) }}%</span>
                </div>
                <div class="d-flex align-center flex-grow-1" style="gap:4px">
                  <span class="text-caption text-warning font-weight-bold" style="min-width:12px">H</span>
                  <v-progress-linear :model-value="searchResult.hold_pct" color="warning" rounded height="5" />
                  <span class="text-caption text-warning" style="min-width:28px; text-align:right">{{ searchResult.hold_pct?.toFixed(0) }}%</span>
                </div>
                <div class="d-flex align-center flex-grow-1" style="gap:4px">
                  <span class="text-caption text-error font-weight-bold" style="min-width:12px">S</span>
                  <v-progress-linear :model-value="searchResult.sell_pct" color="error" rounded height="5" />
                  <span class="text-caption text-error" style="min-width:28px; text-align:right">{{ searchResult.sell_pct?.toFixed(0) }}%</span>
                </div>
              </div>
            </v-card-title>
            <v-divider class="mx-4" />
            <v-card-text class="px-4 py-3">
              <div v-if="searchResult.buy_pct < 50" class="d-flex align-center mb-3" style="gap:6px">
                <v-icon size="16" color="warning">mdi-alert-outline</v-icon>
                <span class="text-caption text-warning">Signal below 50% — not a strong buy at this time</span>
              </div>
              <div class="d-flex flex-wrap mb-3" style="gap:6px">
                <template v-if="searchResult.breakdown">
                  <v-chip v-if="crossChip(searchResult.breakdown.sma_cross)" size="x-small" :color="crossChip(searchResult.breakdown.sma_cross).color" variant="tonal">
                    SMA {{ crossChip(searchResult.breakdown.sma_cross).label }}
                  </v-chip>
                  <v-chip v-if="crossChip(searchResult.breakdown.ema_cross)" size="x-small" :color="crossChip(searchResult.breakdown.ema_cross).color" variant="tonal">
                    EMA {{ crossChip(searchResult.breakdown.ema_cross).label }}
                  </v-chip>
                  <v-chip v-if="searchResult.breakdown.price_vs_sma50 && !searchResult.breakdown.sma_cross" size="x-small" :color="searchResult.breakdown.price_vs_sma50 === 'bullish' ? 'success' : 'error'" variant="tonal">
                    {{ searchResult.breakdown.price_vs_sma50 === 'bullish' ? 'Above SMA 50' : 'Below SMA 50' }}
                  </v-chip>
                  <v-chip v-if="volChip(searchResult.breakdown.volume)" size="x-small" :color="volChip(searchResult.breakdown.volume).color" variant="tonal">
                    {{ volChip(searchResult.breakdown.volume).label }}
                  </v-chip>
                  <v-chip v-if="newsChip(searchResult.breakdown)" size="x-small" :color="newsChip(searchResult.breakdown).color" variant="tonal">
                    {{ newsChip(searchResult.breakdown).label }}
                  </v-chip>
                </template>
              </div>
              <v-sheet rounded="lg" color="transparent" :style="{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)' }" class="pa-3 mb-3">
                <div class="text-caption text-medium-emphasis mb-2 font-weight-medium" style="letter-spacing:0.08em">TRADE SETUP</div>
                <div class="d-flex" style="gap:0; flex-wrap:wrap">
                  <div class="text-center flex-grow-1 px-2"><div class="text-caption text-medium-emphasis">Entry</div><div class="text-body-2 font-weight-bold">{{ fmtPrice(searchResult.entry_price) }}</div></div>
                  <v-divider vertical />
                  <div class="text-center flex-grow-1 px-2"><div class="text-caption text-error">Stop</div><div class="text-body-2 font-weight-bold text-error">{{ fmtPrice(searchResult.stop_loss) }}</div></div>
                  <v-divider vertical />
                  <div class="text-center flex-grow-1 px-2"><div class="text-caption text-medium-emphasis">T1</div><div class="text-body-2 font-weight-bold text-success">{{ fmtPrice(searchResult.target_1) }}</div></div>
                  <template v-if="searchResult.target_2"><v-divider vertical /><div class="text-center flex-grow-1 px-2"><div class="text-caption text-medium-emphasis">T2</div><div class="text-body-2 font-weight-bold text-success">{{ fmtPrice(searchResult.target_2) }}</div></div></template>
                  <template v-if="searchResult.risk_reward"><v-divider vertical /><div class="text-center flex-grow-1 px-2"><div class="text-caption text-medium-emphasis">R/R</div><div class="text-body-2 font-weight-bold">{{ searchResult.risk_reward }}×</div></div></template>
                </div>
              </v-sheet>
              <div v-if="searchResult.top_news?.length">
                <div class="text-caption text-medium-emphasis mb-1 font-weight-medium" style="letter-spacing:0.08em">LATEST NEWS</div>
                <v-list density="compact" class="pa-0">
                  <v-list-item v-for="(n, i) in searchResult.top_news" :key="i" :href="n.url" target="_blank" class="px-0" rounded="lg" min-height="36">
                    <template #prepend><v-icon size="8" :color="sentimentColor(n.sentiment)" class="mr-2">mdi-circle</v-icon></template>
                    <v-list-item-title class="text-caption" style="white-space:normal; line-height:1.3">{{ n.title }}</v-list-item-title>
                    <v-list-item-subtitle class="text-caption text-disabled">{{ n.publisher }} · {{ fmtDate(n.published_at) }}</v-list-item-subtitle>
                  </v-list-item>
                </v-list>
              </div>
            </v-card-text>
            <v-card-actions class="px-4 pb-3">
              <v-spacer />
              <v-btn size="small" variant="tonal" color="primary" append-icon="mdi-arrow-right" @click="openDashboard(searchResult.ticker)">Open Dashboard</v-btn>
            </v-card-actions>
          </v-card>
        </v-col>
      </v-row>
      <v-divider class="mb-4" />
    </template>

    <!-- Loading -->
    <v-progress-linear v-if="loading" indeterminate color="warning" class="mb-4" rounded />

    <!-- Error -->
    <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</v-alert>

    <!-- Empty: no portfolio/watchlist tickers at all -->
    <div v-else-if="!loading && recs.length === 0 && !error" class="text-center py-16">
      <v-icon size="64" color="medium-emphasis" class="mb-4">mdi-chart-timeline-variant-shimmer</v-icon>
      <div class="text-body-1 text-medium-emphasis mb-1">No strong buy signals right now</div>
      <div class="text-caption text-disabled">
        Add stocks to your portfolio or watchlists — or the market may just be mixed. Check back later.
      </div>
    </div>

    <!-- Cards grid -->
    <v-row v-else>
      <v-col v-for="rec in recs" :key="rec.ticker" cols="12" md="6">
        <v-card rounded="lg" border>
          <!-- Card header -->
          <v-card-title class="pt-4 pb-1 px-4">
            <div class="d-flex align-center" style="gap:10px; flex-wrap:wrap">
              <!-- Ticker chip navigates to dashboard -->
              <v-btn
                variant="tonal"
                size="small"
                rounded="lg"
                color="primary"
                @click="openDashboard(rec.ticker)"
              >{{ rec.ticker }}</v-btn>

              <span class="text-body-2 text-medium-emphasis flex-grow-1" style="min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">
                {{ rec.company_name || '' }}
              </span>

              <!-- Buy % -->
              <v-chip size="small" :color="buyChipColor(rec.buy_pct)" variant="flat" class="font-weight-bold">
                BUY {{ rec.buy_pct.toFixed(0) }}%
              </v-chip>
            </div>

            <!-- Price row -->
            <div class="d-flex align-center mt-1" style="gap:8px">
              <span class="text-h6 font-weight-bold">{{ fmtPrice(rec.current_price) }}</span>
              <span v-if="rec.day_change != null" :class="chgColor(rec.day_change)" class="text-body-2">
                {{ fmtChg(rec.day_change) }} ({{ fmtPct(rec.day_change_pct) }})
              </span>
            </div>
            <!-- B / H / S mini bars -->
            <div class="d-flex align-center mt-2" style="gap:10px">
              <div class="d-flex align-center flex-grow-1" style="gap:4px">
                <span class="text-caption text-success font-weight-bold" style="min-width:12px">B</span>
                <v-progress-linear :model-value="rec.buy_pct" color="success" rounded height="5" />
                <span class="text-caption text-success" style="min-width:28px; text-align:right">{{ rec.buy_pct?.toFixed(0) }}%</span>
              </div>
              <div class="d-flex align-center flex-grow-1" style="gap:4px">
                <span class="text-caption text-warning font-weight-bold" style="min-width:12px">H</span>
                <v-progress-linear :model-value="rec.hold_pct" color="warning" rounded height="5" />
                <span class="text-caption text-warning" style="min-width:28px; text-align:right">{{ rec.hold_pct?.toFixed(0) }}%</span>
              </div>
              <div class="d-flex align-center flex-grow-1" style="gap:4px">
                <span class="text-caption text-error font-weight-bold" style="min-width:12px">S</span>
                <v-progress-linear :model-value="rec.sell_pct" color="error" rounded height="5" />
                <span class="text-caption text-error" style="min-width:28px; text-align:right">{{ rec.sell_pct?.toFixed(0) }}%</span>
              </div>
            </div>
          </v-card-title>

          <v-divider class="mx-4" />

          <v-card-text class="px-4 py-3">

            <!-- WHY chips -->
            <div class="d-flex flex-wrap mb-3" style="gap:6px">
              <template v-if="rec.breakdown">
                <!-- SMA cross -->
                <v-chip
                  v-if="crossChip(rec.breakdown.sma_cross)"
                  size="x-small"
                  :color="crossChip(rec.breakdown.sma_cross).color"
                  variant="tonal"
                >
                  SMA {{ crossChip(rec.breakdown.sma_cross).label }}
                </v-chip>

                <!-- EMA cross -->
                <v-chip
                  v-if="crossChip(rec.breakdown.ema_cross)"
                  size="x-small"
                  :color="crossChip(rec.breakdown.ema_cross).color"
                  variant="tonal"
                >
                  EMA {{ crossChip(rec.breakdown.ema_cross).label }}
                </v-chip>

                <!-- Price vs SMA50 — only show if not a duplicate of the cross signal -->
                <v-chip
                  v-if="rec.breakdown.price_vs_sma50 && !rec.breakdown.sma_cross"
                  size="x-small"
                  :color="rec.breakdown.price_vs_sma50 === 'bullish' ? 'success' : 'error'"
                  variant="tonal"
                >
                  {{ rec.breakdown.price_vs_sma50 === 'bullish' ? 'Above SMA 50' : 'Below SMA 50' }}
                </v-chip>

                <!-- Volume -->
                <v-chip
                  v-if="volChip(rec.breakdown.volume)"
                  size="x-small"
                  :color="volChip(rec.breakdown.volume).color"
                  variant="tonal"
                >
                  {{ volChip(rec.breakdown.volume).label }}
                </v-chip>

                <!-- News -->
                <v-chip
                  v-if="newsChip(rec.breakdown)"
                  size="x-small"
                  :color="newsChip(rec.breakdown).color"
                  variant="tonal"
                >
                  {{ newsChip(rec.breakdown).label }}
                </v-chip>
              </template>
            </div>

            <!-- Trade Setup -->
            <v-sheet
              rounded="lg"
              color="transparent"
              :style="{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)' }"
              class="pa-3 mb-3"
            >
              <div class="text-caption text-medium-emphasis mb-2 font-weight-medium" style="letter-spacing:0.08em">
                TRADE SETUP
              </div>
              <div class="d-flex" style="gap:0; flex-wrap:wrap">
                <div class="text-center flex-grow-1 px-2">
                  <div class="text-caption text-medium-emphasis">Entry</div>
                  <div class="text-body-2 font-weight-bold">{{ fmtPrice(rec.entry_price) }}</div>
                </div>
                <v-divider vertical />
                <div class="text-center flex-grow-1 px-2">
                  <div class="text-caption text-error">Stop</div>
                  <div class="text-body-2 font-weight-bold text-error">{{ fmtPrice(rec.stop_loss) }}</div>
                </div>
                <v-divider vertical />
                <div class="text-center flex-grow-1 px-2">
                  <div class="text-caption text-medium-emphasis">T1</div>
                  <div class="text-body-2 font-weight-bold text-success">{{ fmtPrice(rec.target_1) }}</div>
                </div>
                <v-divider vertical v-if="rec.target_2" />
                <div v-if="rec.target_2" class="text-center flex-grow-1 px-2">
                  <div class="text-caption text-medium-emphasis">T2</div>
                  <div class="text-body-2 font-weight-bold text-success">{{ fmtPrice(rec.target_2) }}</div>
                </div>
                <v-divider vertical v-if="rec.risk_reward" />
                <div v-if="rec.risk_reward" class="text-center flex-grow-1 px-2">
                  <div class="text-caption text-medium-emphasis">R/R</div>
                  <div class="text-body-2 font-weight-bold">{{ rec.risk_reward }}×</div>
                </div>
              </div>
            </v-sheet>

            <!-- Top News -->
            <div v-if="rec.top_news && rec.top_news.length">
              <div class="text-caption text-medium-emphasis mb-1 font-weight-medium" style="letter-spacing:0.08em">
                LATEST NEWS
              </div>
              <v-list density="compact" class="pa-0">
                <v-list-item
                  v-for="(n, i) in rec.top_news"
                  :key="i"
                  :href="n.url"
                  target="_blank"
                  class="px-0"
                  rounded="lg"
                  min-height="36"
                >
                  <template #prepend>
                    <v-icon size="8" :color="sentimentColor(n.sentiment)" class="mr-2">mdi-circle</v-icon>
                  </template>
                  <v-list-item-title class="text-caption" style="white-space:normal; line-height:1.3">
                    {{ n.title }}
                  </v-list-item-title>
                  <v-list-item-subtitle class="text-caption text-disabled">
                    {{ n.publisher }} · {{ fmtDate(n.published_at) }}
                  </v-list-item-subtitle>
                </v-list-item>
              </v-list>
            </div>
          </v-card-text>

          <v-card-actions class="px-4 pb-3">
            <v-spacer />
            <v-btn
              size="small"
              variant="tonal"
              color="primary"
              append-icon="mdi-arrow-right"
              @click="openDashboard(rec.ticker)"
            >Open Dashboard</v-btn>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>
