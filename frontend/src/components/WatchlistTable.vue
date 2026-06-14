<script setup>
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import draggable from 'vuedraggable'

const props = defineProps({
  items:      { type: Array,   default: () => [] },
  loading:    { type: Boolean, default: false },
  canReorder: { type: Boolean, default: false },
  showRemove: { type: Boolean, default: false },
})

const emit = defineEmits(['reorder', 'remove'])
const router = useRouter()

// Local copy so draggable can mutate without touching the prop
const localItems = ref([...props.items])
watch(() => props.items, v => { localItems.value = [...v] }, { immediate: true })

// ── Formatters ────────────────────────────────────────────────────────────────
const fmtPrice = v => v != null ? `$${Number(v).toFixed(2)}` : '—'
const fmtChg   = v => v != null ? (v >= 0 ? `+$${v.toFixed(2)}` : `-$${Math.abs(v).toFixed(2)}`) : '—'
const fmtPct   = v => v != null ? (v >= 0 ? `+${v.toFixed(2)}%` : `${v.toFixed(2)}%`) : '—'
const chgColor = v => v == null ? '' : v >= 0 ? 'success' : 'error'
const rowBg    = item => {
  const p = item.day_change_pct
  if (p == null) return {}
  if (p > 0) return { background: 'rgba(76,175,80,0.10)' }
  if (p < 0) return { background: 'rgba(239,83,80,0.10)' }
  return {}
}
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
const rangePct = (lo, hi, cur) => {
  if (!lo || !hi || !cur) return 0
  const r = hi - lo
  return r ? Math.min(100, Math.max(0, Math.round(((cur - lo) / r) * 100))) : 0
}

// ── Search / filter / sort / expand ──────────────────────────────────────────
const searchQuery = ref('')
const filterBy    = ref('all')
const sortKey     = ref(null)
const sortDir     = ref('asc')
const expandedIds = ref(new Set())

function toggleExpand(id) {
  const next = new Set(expandedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedIds.value = next
}

function toggleSort(key) {
  if (sortKey.value === key) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  else { sortKey.value = key; sortDir.value = 'asc' }
}

function sortIcon(key) {
  if (sortKey.value !== key) return 'mdi-unfold-more-horizontal'
  return sortDir.value === 'asc' ? 'mdi-arrow-up' : 'mdi-arrow-down'
}

const filteredItems = computed(() => {
  let result = localItems.value
  const q = searchQuery.value.trim().toLowerCase()
  if (q) result = result.filter(i =>
    i.ticker.toLowerCase().includes(q) || (i.company_name?.toLowerCase().includes(q))
  )
  if (filterBy.value === 'gainers') result = result.filter(i => (i.day_change_pct ?? 0) > 0)
  if (filterBy.value === 'losers')  result = result.filter(i => (i.day_change_pct ?? 0) < 0)
  if (sortKey.value) {
    const k = sortKey.value
    result = [...result].sort((a, b) => {
      const va = a[k] ?? (typeof a[k] === 'string' ? '' : -Infinity)
      const vb = b[k] ?? (typeof b[k] === 'string' ? '' : -Infinity)
      const cmp = typeof va === 'string' ? va.localeCompare(vb) : va - vb
      return sortDir.value === 'asc' ? cmp : -cmp
    })
  }
  return result
})

// Drag is paused when any filter/sort/expand is active, or canReorder is false
const isDragDisabled = computed(() =>
  !props.canReorder ||
  searchQuery.value.trim() !== '' ||
  filterBy.value !== 'all' ||
  sortKey.value !== null ||
  expandedIds.value.size > 0
)

// Number of columns: 1 expand/drag + ticker + company + price + day$ + day% + notes [+ remove]
const colSpan = computed(() => props.showRemove ? 8 : 7)

function onDragEnd() {
  emit('reorder', localItems.value.map(i => i.id))
}
</script>

<template>
  <!-- Loading -->
  <div v-if="loading" class="d-flex justify-center pa-8">
    <v-progress-circular indeterminate />
  </div>

  <template v-else-if="localItems.length">

    <!-- Search + filter row -->
    <div class="pa-4 pb-2">
      <v-row no-gutters align="center" class="ga-3">
        <v-col>
          <v-text-field
            v-model="searchQuery"
            density="compact"
            variant="outlined"
            hide-details
            clearable
            placeholder="Search ticker or company…"
            prepend-inner-icon="mdi-magnify"
          />
        </v-col>
        <v-col cols="auto">
          <v-chip-group v-model="filterBy" mandatory color="primary" density="compact">
            <v-chip value="all"     size="small" variant="tonal">All</v-chip>
            <v-chip value="gainers" size="small" variant="tonal">Gainers</v-chip>
            <v-chip value="losers"  size="small" variant="tonal">Losers</v-chip>
          </v-chip-group>
        </v-col>
      </v-row>
    </div>

    <!-- No results after filtering -->
    <div v-if="!filteredItems.length" class="text-center pa-8">
      <v-icon size="40" color="surface-variant">mdi-filter-off-outline</v-icon>
      <p class="text-body-2 text-medium-emphasis mt-3">No tickers match your search or filter</p>
    </div>

    <v-table v-else density="comfortable">
      <thead>
        <tr>
          <th style="width:40px" />
          <th :style="{ cursor: 'pointer', userSelect: 'none' }" @click="toggleSort('ticker')">
            Ticker <v-icon size="14">{{ sortIcon('ticker') }}</v-icon>
          </th>
          <th :style="{ cursor: 'pointer', userSelect: 'none' }" @click="toggleSort('company_name')">
            Company <v-icon size="14">{{ sortIcon('company_name') }}</v-icon>
          </th>
          <th class="text-right" :style="{ cursor: 'pointer', userSelect: 'none' }" @click="toggleSort('current_price')">
            Price <v-icon size="14">{{ sortIcon('current_price') }}</v-icon>
          </th>
          <th class="text-right" :style="{ cursor: 'pointer', userSelect: 'none' }" @click="toggleSort('day_change')">
            Day Change <v-icon size="14">{{ sortIcon('day_change') }}</v-icon>
          </th>
          <th class="text-right" :style="{ cursor: 'pointer', userSelect: 'none' }" @click="toggleSort('day_change_pct')">
            Change % <v-icon size="14">{{ sortIcon('day_change_pct') }}</v-icon>
          </th>
          <th>Notes</th>
          <th v-if="showRemove" style="width:48px" />
        </tr>
      </thead>

      <!-- Draggable tbody when no sort/filter/expand is active and canReorder is true -->
      <draggable
        v-if="!isDragDisabled"
        v-model="localItems"
        tag="tbody"
        item-key="id"
        handle=".drag-handle"
        @end="onDragEnd"
      >
        <template #item="{ element }">
          <tr :style="rowBg(element)">
            <td>
              <div class="d-flex align-center ga-1">
                <v-icon class="drag-handle text-medium-emphasis" size="18" :style="{ cursor: 'grab' }">mdi-drag</v-icon>
                <v-btn icon size="x-small" variant="text" density="compact" @click="toggleExpand(element.id)">
                  <v-icon size="14">mdi-chevron-down</v-icon>
                </v-btn>
              </div>
            </td>
            <td>
              <v-btn variant="text" color="primary" size="small" class="font-weight-bold px-1"
                @click="router.push(`/dashboard?ticker=${element.ticker}`)">{{ element.ticker }}</v-btn>
            </td>
            <td class="text-body-2">{{ element.company_name || '—' }}</td>
            <td class="text-right text-body-2 font-weight-medium">{{ fmtPrice(element.current_price) }}</td>
            <td class="text-right text-body-2"
              :class="element.day_change != null ? (element.day_change >= 0 ? 'text-success' : 'text-error') : ''">
              {{ fmtChg(element.day_change) }}
            </td>
            <td class="text-right">
              <v-chip v-if="element.day_change_pct != null" :color="chgColor(element.day_change_pct)" size="small" variant="tonal">
                {{ fmtPct(element.day_change_pct) }}
              </v-chip>
              <span v-else class="text-medium-emphasis">—</span>
            </td>
            <td class="text-body-2 text-medium-emphasis">{{ element.notes || '' }}</td>
            <td v-if="showRemove">
              <v-btn icon="mdi-close" size="x-small" variant="text" color="error" @click="emit('remove', element.id)" />
            </td>
          </tr>
        </template>
      </draggable>

      <!-- Plain tbody when sort/filter/expand active — supports expanded rows -->
      <tbody v-else>
        <template v-for="element in filteredItems" :key="element.id">
          <tr :style="rowBg(element)">
            <td>
              <v-btn icon size="x-small" variant="text" density="compact" @click="toggleExpand(element.id)">
                <v-icon size="16">{{ expandedIds.has(element.id) ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
              </v-btn>
            </td>
            <td>
              <v-btn variant="text" color="primary" size="small" class="font-weight-bold px-1"
                @click="router.push(`/dashboard?ticker=${element.ticker}`)">{{ element.ticker }}</v-btn>
            </td>
            <td class="text-body-2">{{ element.company_name || '—' }}</td>
            <td class="text-right text-body-2 font-weight-medium">{{ fmtPrice(element.current_price) }}</td>
            <td class="text-right text-body-2"
              :class="element.day_change != null ? (element.day_change >= 0 ? 'text-success' : 'text-error') : ''">
              {{ fmtChg(element.day_change) }}
            </td>
            <td class="text-right">
              <v-chip v-if="element.day_change_pct != null" :color="chgColor(element.day_change_pct)" size="small" variant="tonal">
                {{ fmtPct(element.day_change_pct) }}
              </v-chip>
              <span v-else class="text-medium-emphasis">—</span>
            </td>
            <td class="text-body-2 text-medium-emphasis">{{ element.notes || '' }}</td>
            <td v-if="showRemove">
              <v-btn icon="mdi-close" size="x-small" variant="text" color="error" @click="emit('remove', element.id)" />
            </td>
          </tr>

          <!-- Expanded detail row — same tint as parent -->
          <tr v-if="expandedIds.has(element.id)" :style="rowBg(element)">
            <td :colspan="colSpan" class="pa-4 pb-3">
              <v-row dense>
                <!-- Day Range -->
                <v-col cols="12" md="5">
                  <p class="text-caption text-medium-emphasis mb-1">Today's Range</p>
                  <v-row no-gutters align="center">
                    <v-col cols="auto" class="text-caption text-error pr-2">{{ fmtPrice(element.day_low) }}</v-col>
                    <v-col>
                      <v-progress-linear
                        :model-value="rangePct(element.day_low, element.day_high, element.current_price)"
                        rounded height="5" color="success" bg-color="rgba(255,255,255,0.08)"
                      />
                    </v-col>
                    <v-col cols="auto" class="text-caption text-success pl-2">{{ fmtPrice(element.day_high) }}</v-col>
                  </v-row>
                </v-col>

                <!-- 52W Range -->
                <v-col cols="12" md="5" class="pl-md-4">
                  <p class="text-caption text-medium-emphasis mb-1">52-Week Range</p>
                  <v-row no-gutters align="center">
                    <v-col cols="auto" class="text-caption text-error pr-2">{{ fmtPrice(element.week_52_low) }}</v-col>
                    <v-col>
                      <v-progress-linear
                        :model-value="rangePct(element.week_52_low, element.week_52_high, element.current_price)"
                        rounded height="5" color="primary" bg-color="rgba(255,255,255,0.08)"
                      />
                    </v-col>
                    <v-col cols="auto" class="text-caption text-success pl-2">{{ fmtPrice(element.week_52_high) }}</v-col>
                  </v-row>
                </v-col>

                <!-- Stats -->
                <v-col cols="12" md="2" class="d-flex flex-wrap ga-4 align-center pl-md-4 pt-2">
                  <div>
                    <p class="text-caption text-medium-emphasis">Prev Close</p>
                    <p class="text-body-2 font-weight-medium">{{ fmtPrice(element.previous_close) }}</p>
                  </div>
                  <div>
                    <p class="text-caption text-medium-emphasis">Market Cap</p>
                    <p class="text-body-2 font-weight-medium">{{ fmtCap(element.market_cap) }}</p>
                  </div>
                  <div>
                    <p class="text-caption text-medium-emphasis">Avg Volume</p>
                    <p class="text-body-2 font-weight-medium">{{ fmtVol(element.avg_volume) }}</p>
                  </div>
                </v-col>

                <!-- After-hours / pre-market -->
                <v-col v-if="element.post_market_price || element.pre_market_price" cols="12" class="pt-2">
                  <v-divider class="mb-3 opacity-20" />
                  <div class="d-flex flex-wrap ga-4">
                    <div v-if="element.post_market_price" class="d-flex align-center ga-2">
                      <v-chip size="x-small" color="deep-purple" variant="tonal">After Hours</v-chip>
                      <span class="text-body-2 font-weight-medium">{{ fmtPrice(element.post_market_price) }}</span>
                      <span :class="element.post_market_change >= 0 ? 'text-success' : 'text-error'" class="text-caption">
                        {{ element.post_market_change >= 0 ? '+' : '' }}{{ fmtPrice(element.post_market_change) }}
                        ({{ element.post_market_change >= 0 ? '+' : '' }}{{ element.post_market_change_pct?.toFixed(2) }}%)
                      </span>
                    </div>
                    <div v-if="element.pre_market_price" class="d-flex align-center ga-2">
                      <v-chip size="x-small" color="orange" variant="tonal">Pre-Market</v-chip>
                      <span class="text-body-2 font-weight-medium">{{ fmtPrice(element.pre_market_price) }}</span>
                      <span :class="element.pre_market_change >= 0 ? 'text-success' : 'text-error'" class="text-caption">
                        {{ element.pre_market_change >= 0 ? '+' : '' }}{{ fmtPrice(element.pre_market_change) }}
                        ({{ element.pre_market_change >= 0 ? '+' : '' }}{{ element.pre_market_change_pct?.toFixed(2) }}%)
                      </span>
                    </div>
                  </div>
                </v-col>
              </v-row>
            </td>
          </tr>
        </template>
      </tbody>
    </v-table>
  </template>

  <!-- Empty state -->
  <div v-else class="text-center pa-12">
    <v-icon size="56" color="surface-variant">mdi-chart-line-variant</v-icon>
    <p class="text-body-1 text-medium-emphasis mt-4">No tickers yet</p>
    <p class="text-body-2 text-medium-emphasis">Type tickers or paste a Yahoo Finance URL above and click Add</p>
  </div>
</template>
