<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import api from './api'
import { pageGradientOverride } from './pageState'

const drawer = ref(true)

// ── Market ticker state ───────────────────────────────────────────────────────
const markets = ref([])

// When all items carry is_futures=true the backend is in futures mode (after hours / weekends).
const isFutures = computed(() => markets.value.length > 0 && markets.value[0].is_futures)

// Debounce guard: skip the fetch if a previous one is still in flight.
// This prevents request stacking when a slow network takes longer than the interval.
let isFetching = false
async function fetchMarkets() {
  if (isFetching) return
  isFetching = true
  try {
    const res = await api.get('/stocks/markets')
    markets.value = res.data
  } catch {}
  finally { isFetching = false }
}

// Nasdaq determines the default gradient; Dashboard overrides via pageGradientOverride.
const nasdaqItem = computed(() => markets.value.find(m => m.label.startsWith('Nasdaq')))

// 'up' | 'down' | null
const effectiveDir = computed(() => {
  if (pageGradientOverride.value) return pageGradientOverride.value
  if (!nasdaqItem.value) return null
  return nasdaqItem.value.change_pct >= 0 ? 'up' : 'down'
})

// rgb channel string for the gradient colour (no alpha yet)
const gradientRgb = computed(() =>
  effectiveDir.value === 'up' ? '76,175,80' : effectiveDir.value === 'down' ? '239,83,80' : null
)

// App bar: strong tint at the very top, fades to the surface colour at the bottom
const appBarStyle = computed(() => {
  if (!gradientRgb.value) return {}
  return {
    'background-image': `linear-gradient(180deg, rgba(${gradientRgb.value},0.28) 0%, transparent 100%)`,
  }
})

// Page body: light tint from the top that fades out over ~320px
const mainStyle = computed(() => {
  if (!gradientRgb.value) return {}
  return {
    'background-image': `linear-gradient(180deg, rgba(${gradientRgb.value},0.13) 0%, transparent 320px)`,
  }
})

// ── Formatters ────────────────────────────────────────────────────────────────
// Comma-formatted price with 2 decimal places (no currency symbol — indices are dimensionless).
const fmtPrice  = v => v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const fmtChange = v => (v >= 0 ? '+' : '') + v.toFixed(2)
const fmtPct    = v => (v >= 0 ? '+' : '') + v.toFixed(2) + '%'
const changeColor = v => v >= 0 ? 'text-success' : 'text-error'

// ── Lifecycle ─────────────────────────────────────────────────────────────────
let dataTimer = null

onMounted(() => {
  fetchMarkets()
  // Refresh every 60 seconds. Yahoo Finance data has a 15-min delay, so faster
  // intervals return identical data while burning through rate limits unnecessarily.
  dataTimer = setInterval(fetchMarkets, 60_000)
})

onUnmounted(() => clearInterval(dataTimer))
</script>

<template>
  <v-app>
    <v-navigation-drawer v-model="drawer" permanent width="220" :style="mainStyle">
      <v-list-item
        prepend-icon="mdi-chart-line"
        title="Stock Analyzer"
        nav
        class="py-5"
      />
      <v-divider />
      <v-list nav density="compact" class="mt-2">
        <v-list-item
          to="/dashboard"
          prepend-icon="mdi-view-dashboard-outline"
          title="Dashboard"
          rounded="lg"
        />
        <v-list-item
          to="/recommendations"
          prepend-icon="mdi-lightbulb-outline"
          title="Recommendations"
          rounded="lg"
        />
        <v-list-item
          to="/portfolio"
          prepend-icon="mdi-briefcase-outline"
          title="Portfolio"
          rounded="lg"
        />
        <v-list-item
          to="/watchlist"
          prepend-icon="mdi-star-outline"
          title="Watchlist"
          rounded="lg"
        />
        <v-list-item
          to="/history"
          prepend-icon="mdi-history"
          title="History"
          rounded="lg"
        />
        <v-list-item
          to="/news"
          prepend-icon="mdi-newspaper-variant-outline"
          title="News"
          rounded="lg"
        />
        <v-list-item
          to="/intel"
          prepend-icon="mdi-radar"
          title="Market Intel"
          rounded="lg"
        />
      </v-list>
    </v-navigation-drawer>

    <v-app-bar flat border="b" color="surface" :style="appBarStyle">
      <v-app-bar-nav-icon @click="drawer = !drawer" />

      <!-- App title -->
      <span class="text-body-2 font-weight-medium text-no-wrap mx-2">Stock Analyzer</span>

      <v-divider vertical class="my-3 mx-2" />

      <!-- Mode label: "Markets" during session, "Futures" outside hours -->
      <v-icon size="14" class="mr-1" :color="isFutures ? 'warning' : 'medium-emphasis'">
        {{ isFutures ? 'mdi-clock-outline' : 'mdi-earth' }}
      </v-icon>
      <span class="text-caption text-no-wrap mr-3" :class="isFutures ? 'text-warning' : 'text-medium-emphasis'">
        {{ isFutures ? 'Futures' : 'Markets' }}
      </span>

      <!-- Static market items — each takes an equal share of the remaining app-bar width -->
      <template v-if="markets.length">
        <div
          v-for="(item, idx) in markets"
          :key="item.ticker"
          :style="{
            flex: '1 1 0',
            minWidth: 0,
            padding: '0 10px',
            borderLeft: idx > 0 ? '1px solid rgba(255,255,255,0.08)' : 'none',
          }"
        >
          <div class="text-caption text-medium-emphasis text-truncate">{{ item.label }}</div>
          <div class="text-body-2 font-weight-bold text-no-wrap">{{ fmtPrice(item.price) }}</div>
          <div :class="changeColor(item.change)" class="text-caption text-no-wrap">
            {{ fmtChange(item.change) }}&nbsp;{{ fmtPct(item.change_pct) }}
          </div>
        </div>
      </template>

      <!-- Skeleton while the first fetch is in flight -->
      <div v-else :style="{ flex: '1 1 0' }" class="px-4">
        <v-skeleton-loader type="text" width="300" />
      </div>
    </v-app-bar>

    <v-main :style="mainStyle">
      <router-view />
    </v-main>
  </v-app>
</template>
