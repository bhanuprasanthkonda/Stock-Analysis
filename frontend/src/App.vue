<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import api from './api'

const drawer = ref(true)

// ── Market ticker state ───────────────────────────────────────────────────────
const markets = ref([])

// When all items carry is_futures=true the backend is in futures mode (after hours / weekends).
const isFutures = computed(() => markets.value.length > 0 && markets.value[0].is_futures)

// Fetch all 8 market items. Called on mount and every 15 seconds.
async function fetchMarkets() {
  try {
    const res = await api.get('/stocks/markets')
    markets.value = res.data
  } catch {}
}

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
  // Refresh market data every 15 seconds.
  dataTimer = setInterval(fetchMarkets, 15_000)
})

onUnmounted(() => clearInterval(dataTimer))
</script>

<template>
  <v-app>
    <v-navigation-drawer v-model="drawer" permanent width="220">
      <v-list-item
        prepend-icon="mdi-chart-line"
        title="Stock Analyzer"
        nav
        class="py-4"
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
          to="/portfolio"
          prepend-icon="mdi-briefcase-outline"
          title="Portfolio"
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
      </v-list>
    </v-navigation-drawer>

    <v-app-bar flat border="b" color="surface">
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

    <v-main>
      <router-view />
    </v-main>
  </v-app>
</template>
