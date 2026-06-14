<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'

const activeTab = ref('news')

// ── Market News ───────────────────────────────────────────────────────────────
const marketNews    = ref([])
const newsLoading   = ref(false)
const newsError     = ref(null)

async function fetchMarketNews() {
  newsLoading.value = true
  newsError.value   = null
  try {
    marketNews.value = (await api.get('/intel/market-news')).data
  } catch {
    newsError.value = 'Could not load market news.'
  } finally {
    newsLoading.value = false
  }
}

// ── Economic Calendar ─────────────────────────────────────────────────────────
const calEvents  = ref([])
const calLoading = ref(false)
const calLoaded  = ref(false)
const calError   = ref(null)

async function fetchCalendar() {
  calLoading.value = true
  calError.value   = null
  try {
    calEvents.value = (await api.get('/intel/economic-calendar')).data
    calLoaded.value = true
  } catch {
    calError.value = 'Could not load economic calendar.'
  } finally {
    calLoading.value = false
  }
}

function onTabChange(tab) {
  activeTab.value = tab
  if (tab === 'calendar' && !calLoaded.value) fetchCalendar()
}

onMounted(fetchMarketNews)

// ── Formatters ────────────────────────────────────────────────────────────────
const sentimentColor = s => s === 'good' ? 'success' : s === 'bad' ? 'error' : 'warning'

function fmtDate(iso) {
  if (!iso) return ''
  try { return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) }
  catch { return iso }
}

function importanceColor(imp) {
  if (imp === 'High')   return 'error'
  if (imp === 'Medium') return 'warning'
  return 'default'
}

function categoryIcon(cat) {
  const map = {
    'Employment':      'mdi-account-group-outline',
    'Inflation':       'mdi-fire',
    'GDP':             'mdi-trending-up',
    'Federal Reserve': 'mdi-bank-outline',
    'Retail':          'mdi-shopping-outline',
    'Housing':         'mdi-home-outline',
    'Trade':           'mdi-ship-wheel',
    'Manufacturing':   'mdi-factory',
  }
  return map[cat] || 'mdi-calendar-clock'
}
</script>

<template>
  <v-container class="pa-6" max-width="1400">
    <!-- Header -->
    <div class="d-flex align-center mb-4" style="gap:12px">
      <v-icon size="28" color="primary">mdi-radar</v-icon>
      <div>
        <div class="text-h5 font-weight-bold">Market Intelligence</div>
        <div class="text-caption text-medium-emphasis">Market-moving news · Economic calendar</div>
      </div>
    </div>

    <!-- Tabs -->
    <v-tabs v-model="activeTab" color="primary" class="mb-4" @update:model-value="onTabChange">
      <v-tab value="news"     prepend-icon="mdi-newspaper-variant-outline">Market News</v-tab>
      <v-tab value="calendar" prepend-icon="mdi-calendar-clock">Economic Calendar</v-tab>
    </v-tabs>

    <v-window v-model="activeTab">

      <!-- ── TAB 1: Market News ──────────────────────────────────────────── -->
      <v-window-item value="news">
        <div class="d-flex justify-end mb-3">
          <v-btn size="small" variant="tonal" prepend-icon="mdi-refresh" @click="fetchMarketNews" :loading="newsLoading">
            Refresh
          </v-btn>
        </div>
        <v-progress-linear v-if="newsLoading" indeterminate color="primary" rounded class="mb-4" />
        <v-alert v-if="newsError" type="error" variant="tonal" class="mb-4">{{ newsError }}</v-alert>

        <div v-if="!newsLoading && marketNews.length === 0 && !newsError" class="text-center py-12 text-medium-emphasis">
          <v-icon size="48" class="mb-3">mdi-newspaper-variant-outline</v-icon>
          <div>No market news available right now.</div>
        </div>

        <v-table density="compact" v-if="marketNews.length">
          <thead>
            <tr>
              <th style="width:110px">Source</th>
              <th>Headline</th>
              <th style="width:110px">Publisher</th>
              <th style="width:90px">Sentiment</th>
              <th style="width:80px">Date</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(n, i) in marketNews" :key="i">
              <td>
                <v-chip size="x-small" variant="tonal" color="primary">{{ n.source_label }}</v-chip>
              </td>
              <td>
                <a :href="n.url" target="_blank" class="text-decoration-none text-body-2" style="color:inherit">
                  {{ n.title }}
                </a>
              </td>
              <td class="text-caption text-medium-emphasis">{{ n.publisher }}</td>
              <td>
                <v-chip size="x-small" :color="sentimentColor(n.sentiment)" variant="flat">
                  {{ n.sentiment }}
                </v-chip>
              </td>
              <td class="text-caption text-medium-emphasis">{{ fmtDate(n.published_at) }}</td>
            </tr>
          </tbody>
        </v-table>
      </v-window-item>

      <!-- ── TAB 2: Economic Calendar ────────────────────────────────────── -->
      <v-window-item value="calendar">
        <div class="d-flex justify-end mb-3">
          <v-btn size="small" variant="tonal" prepend-icon="mdi-refresh" @click="fetchCalendar" :loading="calLoading">
            Refresh
          </v-btn>
        </div>
        <v-progress-linear v-if="calLoading" indeterminate color="primary" rounded class="mb-4" />
        <v-alert v-if="calError" type="error" variant="tonal" class="mb-4">{{ calError }}</v-alert>

        <div v-if="!calLoading && calLoaded && calEvents.length === 0" class="text-center py-12 text-medium-emphasis">
          <v-icon size="48" class="mb-3">mdi-calendar-clock</v-icon>
          <div>No events found in the current window.</div>
        </div>

        <v-table density="comfortable" v-if="calEvents.length">
          <thead>
            <tr>
              <th style="width:160px">Date</th>
              <th style="width:100px">Time (ET)</th>
              <th>Event</th>
              <th style="width:140px">Category</th>
              <th style="width:100px">Importance</th>
              <th style="width:100px">Source</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(ev, i) in calEvents"
              :key="i"
              :style="ev.is_today
                ? 'background:rgba(var(--v-theme-primary),0.12); outline:1px solid rgba(var(--v-theme-primary),0.35)'
                : ev.is_past ? 'opacity:0.5' : ''"
            >
              <td class="text-body-2 font-weight-medium">
                {{ ev.date }}
                <v-chip v-if="ev.is_today" size="x-small" color="primary" variant="flat" class="ml-1">TODAY</v-chip>
              </td>
              <td class="text-caption text-medium-emphasis">{{ ev.time }}</td>
              <td>
                <div class="d-flex align-center" style="gap:8px">
                  <v-icon size="16" :color="importanceColor(ev.importance)">{{ categoryIcon(ev.category) }}</v-icon>
                  <span class="text-body-2">{{ ev.event }}</span>
                </div>
              </td>
              <td>
                <v-chip size="x-small" variant="tonal" color="default">{{ ev.category }}</v-chip>
              </td>
              <td>
                <v-chip size="x-small" :color="importanceColor(ev.importance)" variant="flat">
                  {{ ev.importance }}
                </v-chip>
              </td>
              <td class="text-caption text-medium-emphasis">{{ ev.source }}</td>
            </tr>
          </tbody>
        </v-table>
      </v-window-item>

    </v-window>
  </v-container>
</template>
