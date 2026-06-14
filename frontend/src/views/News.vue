<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()

const allNews = ref([])
const loading = ref(false)
const searchInput = ref('')
const suggestions = ref([])
const suggesting = ref(false)
const selectedTicker = ref(null)
const searchHistory = ref([])
const loadedTickers = ref(new Set())
const lastRefreshed = ref(null)
let suggestTimer = null
let refreshTimer = null

// ── Load search history chips ─────────────────────────────────────────────────

// Populates the history chip row so users can quickly toggle previously searched tickers.
async function fetchSearchHistory() {
  try {
    const res = await api.get('/portfolio/history')
    searchHistory.value = res.data
  } catch {}
}

// ── Load news from portfolio holdings on mount ────────────────────────────────

// On first load, auto-fetch news for up to 8 portfolio tickers in parallel so the
// page isn't empty. Individual failures are swallowed so one bad ticker doesn't
// block the rest.
async function loadPortfolioNews() {
  loading.value = true
  try {
    const posRes = await api.get('/portfolio/positions')
    const tickers = [...new Set(posRes.data.map(p => p.ticker))].slice(0, 8)
    if (!tickers.length) return
    const results = await Promise.all(
      tickers.map(t =>
        api.get(`/stocks/${t}/news`)
          .then(r => { loadedTickers.value.add(t); return r.data.map(n => ({ ...n, source_ticker: t })) })
          .catch(() => [])
      )
    )
    mergeNews(results.flat())
    lastRefreshed.value = new Date()
  } catch {}
  finally { loading.value = false }
}

// ── Add / remove news for a ticker ───────────────────────────────────────────

// Remove all articles tagged with `ticker` and untrack it from loadedTickers.
// loadedTickers is a Set ref — must replace with a new Set to trigger reactivity.
function removeTickerNews(ticker) {
  allNews.value = allNews.value.filter(n => n.source_ticker !== ticker)
  const next = new Set(loadedTickers.value)
  next.delete(ticker)
  loadedTickers.value = next
}

// Fetch and merge news for a ticker, then mark it loaded. Clears the search
// input on completion so the autocomplete resets for the next lookup.
async function addTickerNews(ticker) {
  if (!ticker) return
  ticker = ticker.trim().toUpperCase()
  loading.value = true
  try {
    const res = await api.get(`/stocks/${ticker}/news`)
    loadedTickers.value = new Set([...loadedTickers.value, ticker])
    mergeNews(res.data.map(n => ({ ...n, source_ticker: ticker })))
    // Extract company name from the autocomplete suggestion label ("AAPL — Apple Inc.")
    // before suggestions are cleared in the finally block.
    const match = suggestions.value.find(s => s.ticker === ticker)
    const companyName = match ? match.label.split(' — ').slice(1).join(' — ') : null
    const histParams = companyName
      ? `ticker=${ticker}&company_name=${encodeURIComponent(companyName)}`
      : `ticker=${ticker}`
    api.post(`/portfolio/history?${histParams}`).catch(() => {})
    fetchSearchHistory()
  } catch {}
  finally {
    loading.value = false
    selectedTicker.value = null
    searchInput.value = ''
    suggestions.value = []
  }
}

// Toggle: remove if already loaded (deselect), add if not (select).
function toggleTicker(ticker) {
  if (loadedTickers.value.has(ticker)) removeTickerNews(ticker)
  else addTickerNews(ticker)
}

// ── Refresh ───────────────────────────────────────────────────────────────────

// Re-fetch news for every currently loaded ticker, replace all articles, and
// update the lastRefreshed timestamp. Silently skips if no tickers are loaded.
async function refreshNews() {
  const tickers = [...loadedTickers.value]
  if (!tickers.length) return
  loading.value = true
  try {
    const results = await Promise.all(
      tickers.map(t =>
        api.get(`/stocks/${t}/news`)
          .then(r => r.data.map(n => ({ ...n, source_ticker: t })))
          .catch(() => [])
      )
    )
    // Full replace (not merge) so stale articles are removed on refresh.
    allNews.value = results.flat()
      .sort((a, b) => new Date(b.published_at) - new Date(a.published_at))
    lastRefreshed.value = new Date()
  } catch {}
  finally { loading.value = false }
}

// De-duplicate incoming articles by title before appending, then sort newest-first.
// Dedup by title (not URL) because the same article can appear under multiple tickers.
function mergeNews(incoming) {
  const existing = new Set(allNews.value.map(n => n.title))
  const fresh = incoming.filter(n => !existing.has(n.title))
  allNews.value = [...allNews.value, ...fresh]
    .sort((a, b) => new Date(b.published_at) - new Date(a.published_at))
}

// ── Company / ticker autocomplete ─────────────────────────────────────────────

// Debounced search — waits 300ms after typing stops before hitting the backend.
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

// Called when user picks a dropdown suggestion — val is already a ticker string.
function onTickerSelect(val) {
  if (val) addTickerNews(val)
}

// Handles manual Enter press when no dropdown item is selected.
function onEnterKey() {
  const raw = searchInput.value?.trim().toUpperCase()
  if (raw) addTickerNews(raw)
}

// Navigate to Dashboard with the ticker pre-loaded (deep link via ?ticker=).
function goToDashboard(ticker) {
  router.push({ path: '/dashboard', query: { ticker } })
}

onMounted(() => {
  fetchSearchHistory()
  loadPortfolioNews()
  // Auto-refresh every 5 minutes while the page is open.
  refreshTimer = setInterval(refreshNews, 5 * 60 * 1000)
})

onUnmounted(() => {
  clearInterval(refreshTimer)
})

// ── Table ─────────────────────────────────────────────────────────────────────
const headers = [
  { title: 'Ticker',    key: 'source_ticker', width: '90px' },
  { title: 'Headline',  key: 'title',         width: '45%' },
  { title: 'Related',   key: 'related_tickers', width: '140px', sortable: false },
  { title: 'Publisher', key: 'publisher',     width: '120px' },
  { title: 'Sentiment', key: 'sentiment',     width: '110px' },
  { title: 'Date',      key: 'published_at',  width: '140px' },
]

const sentimentColor = s => s === 'good' ? 'success' : s === 'bad' ? 'error' : 'default'
const sentimentIcon  = s => s === 'good' ? 'mdi-trending-up' : s === 'bad' ? 'mdi-trending-down' : 'mdi-minus'
const fmtDate = iso => iso ? new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'
</script>

<template>
  <v-container fluid class="pa-6">

    <!-- Header + search -->
    <v-row align="center" class="mb-4">
      <v-col>
        <span class="text-h6 font-weight-medium">
          <v-icon size="20" class="mr-2">mdi-newspaper-variant-outline</v-icon>
          Latest News
        </span>
        <span v-if="lastRefreshed" class="text-caption text-medium-emphasis ml-3">
          Updated {{ lastRefreshed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }}
        </span>
      </v-col>
      <v-col cols="auto" class="d-flex align-center ga-1">
        <v-btn
          v-if="loadedTickers.size"
          variant="tonal"
          color="primary"
          size="small"
          :loading="loading"
          prepend-icon="mdi-refresh"
          @click="refreshNews"
        >
          Refresh
        </v-btn>
        <v-btn
          v-if="allNews.length"
          variant="text"
          color="error"
          size="small"
          prepend-icon="mdi-delete-outline"
          @click="allNews = []; loadedTickers = new Set(); lastRefreshed = null"
        >
          Clear
        </v-btn>
      </v-col>
      <v-col cols="12" sm="5" md="4">
        <v-autocomplete
          v-model="selectedTicker"
          v-model:search="searchInput"
          :items="suggestions"
          item-title="label"
          item-value="ticker"
          :return-object="false"
          no-filter
          clearable
          hide-no-data
          hide-details
          density="comfortable"
          variant="outlined"
          label="Add ticker or company…"
          placeholder="AAPL, Apple, Tesla…"
          :loading="suggesting"
          append-inner-icon="mdi-plus"
          @update:search="onSearchType"
          @update:model-value="onTickerSelect"
          @keydown.enter.prevent="onEnterKey"
          @click:append-inner="onEnterKey"
        />
      </v-col>
    </v-row>

    <!-- Search history chips — top 10, wrap naturally into 2 rows -->
    <v-row v-if="searchHistory.length" class="mb-4">
      <v-col cols="12">
        <div class="d-flex align-center ga-1 mb-2">
          <v-icon size="13" color="medium-emphasis">mdi-history</v-icon>
          <span class="text-overline text-medium-emphasis">Recent Searches</span>
        </div>
        <div class="d-flex flex-wrap ga-2">
          <v-chip
            v-for="h in searchHistory.slice(0, 10)"
            :key="h.ticker"
            size="small"
            :variant="loadedTickers.has(h.ticker) ? 'flat' : 'tonal'"
            :color="loadedTickers.has(h.ticker) ? 'primary' : 'default'"
            @click="toggleTicker(h.ticker)"
          >
            <span class="font-weight-medium">{{ h.ticker }}</span>
            <span v-if="h.company_name" class="text-caption ml-1 opacity-70">· {{ h.company_name }}</span>
            <v-icon v-if="loadedTickers.has(h.ticker)" end size="12">mdi-check</v-icon>
          </v-chip>
        </div>
      </v-col>
    </v-row>

    <v-card rounded="lg">
      <v-data-table
        :items="allNews"
        :headers="headers"
        :loading="loading"
        density="comfortable"
        :items-per-page="25"
        no-data-text="No news yet — add a ticker above or add positions to your Portfolio"
      >
        <!-- Source ticker -->
        <template #item.source_ticker="{ item }">
          <v-btn
            variant="text"
            size="small"
            color="primary"
            class="font-weight-bold px-1"
            @click="goToDashboard(item.source_ticker)"
          >
            {{ item.source_ticker }}
          </v-btn>
        </template>

        <!-- Headline (link) -->
        <template #item.title="{ item }">
          <a
            v-if="item.url"
            :href="item.url"
            target="_blank"
            class="text-body-2 text-primary text-decoration-none"
          >
            {{ item.title }}
          </a>
          <span v-else class="text-body-2">{{ item.title }}</span>
        </template>

        <!-- Related tickers -->
        <template #item.related_tickers="{ item }">
          <v-chip
            v-for="t in (item.related_tickers || []).slice(0, 3)"
            :key="t"
            size="x-small"
            variant="tonal"
            color="secondary"
            label
            class="mr-1"
            @click="goToDashboard(t)"
          >
            {{ t }}
          </v-chip>
        </template>

        <!-- Sentiment -->
        <template #item.sentiment="{ item }">
          <v-chip
            size="x-small"
            :color="sentimentColor(item.sentiment)"
            variant="tonal"
            label
          >
            <v-icon start size="10">{{ sentimentIcon(item.sentiment) }}</v-icon>
            {{ item.sentiment }}
          </v-chip>
        </template>

        <!-- Date -->
        <template #item.published_at="{ item }">
          <span class="text-caption text-medium-emphasis">{{ fmtDate(item.published_at) }}</span>
        </template>
      </v-data-table>
    </v-card>

  </v-container>
</template>
