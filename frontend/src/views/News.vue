<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()

const allNews = ref([])
const loading = ref(false)
const searchInput = ref('')
const suggestions = ref([])
const suggesting = ref(false)
const selectedTicker = ref(null)
let suggestTimer = null

// ── Load news from portfolio holdings on mount ────────────────────────────────
async function loadPortfolioNews() {
  loading.value = true
  try {
    const posRes = await api.get('/portfolio/positions')
    const tickers = [...new Set(posRes.data.map(p => p.ticker))].slice(0, 8)
    if (!tickers.length) return
    const results = await Promise.all(
      tickers.map(t =>
        api.get(`/stocks/${t}/news`)
          .then(r => r.data.map(n => ({ ...n, source_ticker: t })))
          .catch(() => [])
      )
    )
    mergeNews(results.flat())
  } catch {}
  finally { loading.value = false }
}

// ── Add news for a specific ticker ────────────────────────────────────────────
async function addTickerNews(ticker) {
  if (!ticker) return
  ticker = ticker.trim().toUpperCase()
  loading.value = true
  try {
    const res = await api.get(`/stocks/${ticker}/news`)
    mergeNews(res.data.map(n => ({ ...n, source_ticker: ticker })))
  } catch (e) {
    // silently ignore if ticker not found
  } finally {
    loading.value = false
    selectedTicker.value = null
    searchInput.value = ''
    suggestions.value = []
  }
}

function mergeNews(incoming) {
  const existing = new Set(allNews.value.map(n => n.title))
  const fresh = incoming.filter(n => !existing.has(n.title))
  allNews.value = [...allNews.value, ...fresh]
    .sort((a, b) => new Date(b.published_at) - new Date(a.published_at))
}

// ── Company / ticker autocomplete ─────────────────────────────────────────────
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

function onTickerSelect(val) {
  if (val) addTickerNews(val)
}

function onEnterKey() {
  const raw = searchInput.value?.trim().toUpperCase()
  if (raw) addTickerNews(raw)
}

function goToDashboard(ticker) {
  router.push({ path: '/dashboard', query: { ticker } })
}

onMounted(loadPortfolioNews)

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
      </v-col>
      <v-col cols="auto">
        <v-btn
          v-if="allNews.length"
          variant="text"
          color="error"
          size="small"
          prepend-icon="mdi-delete-outline"
          @click="allNews = []"
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
