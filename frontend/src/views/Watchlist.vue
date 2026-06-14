<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import api from '../api'
import WatchlistTable from '../components/WatchlistTable.vue'

const router = useRouter()
const route  = useRoute()

// ── State ─────────────────────────────────────────────────────────────────────
const watchlists   = ref([])
const selectedId   = ref(null)
const items        = ref([])
const loadingLists = ref(false)
const loadingItems = ref(false)

const tickerInput  = ref('')
const addingItems  = ref(false)

const newDialog    = ref(false)
const newName      = ref('')
const creatingList = ref(false)

const renameDialog = ref(false)
const renameId     = ref(null)
const renameName   = ref('')
const renamingList = ref(false)

// Share snackbar + fallback dialog
const snackbar     = ref(false)
const snackbarMsg  = ref('')
const shareFallback      = ref(false)
const shareFallbackUrl   = ref('')

// Import dialog (shown when page loads with ?tickers= param or a share URL is pasted)
const importDialog  = ref(false)
const importTickers = ref('')
const importName    = ref('')
const importDest    = ref(null)   // watchlist id to import into; null = create new
const importingList = ref(false)

// ── Ticker input parser ───────────────────────────────────────────────────────
// Accepts: plain tickers ("AAPL, MSFT"), Yahoo Finance URLs (/quotes/AAPL,MSFT/),
// or our own share URLs (?tickers=AAPL,MSFT).
function parseTickerString(raw) {
  const t = raw.trim()
  // Yahoo Finance: https://finance.yahoo.com/quotes/RKLB,ASTS,PL/
  const yahooMatch = t.match(/\/quotes\/([A-Z0-9%,.-]+)/i)
  if (yahooMatch) return decodeURIComponent(yahooMatch[1])
  // Our share URL: ?tickers=AAPL,MSFT&name=...
  try {
    const url = new URL(t)
    const p = url.searchParams.get('tickers')
    if (p) return p
  } catch {}
  // Plain comma-separated
  return t
}

// ── Watchlists ────────────────────────────────────────────────────────────────
async function fetchWatchlists() {
  loadingLists.value = true
  try {
    const res = await api.get('/watchlist/')
    watchlists.value = res.data
    if (selectedId.value === null && res.data.length) {
      selectWatchlist(res.data[0].id)
    }
  } catch { /* non-critical */ }
  finally { loadingLists.value = false }
}

function selectWatchlist(id) {
  selectedId.value = id
  fetchItems()
}

async function createWatchlist() {
  const name = newName.value.trim()
  if (!name) return
  creatingList.value = true
  try {
    const res = await api.post('/watchlist/', { name })
    newDialog.value = false
    newName.value = ''
    await fetchWatchlists()
    selectWatchlist(res.data.id)
  } catch { /* ignore */ }
  finally { creatingList.value = false }
}

function openRename(wl) {
  renameId.value    = wl.id
  renameName.value  = wl.name
  renameDialog.value = true
}

async function renameWatchlist() {
  const name = renameName.value.trim()
  if (!name || !renameId.value) return
  renamingList.value = true
  try {
    await api.patch(`/watchlist/${renameId.value}`, { name })
    const wl = watchlists.value.find(w => w.id === renameId.value)
    if (wl) wl.name = name
    renameDialog.value = false
  } catch { /* ignore */ }
  finally { renamingList.value = false }
}

async function deleteWatchlist(id) {
  try {
    await api.delete(`/watchlist/${id}`)
    if (selectedId.value === id) { selectedId.value = null; items.value = [] }
    await fetchWatchlists()
    if (selectedId.value === null && watchlists.value.length) {
      selectWatchlist(watchlists.value[0].id)
    }
  } catch { /* ignore */ }
}

// ── Share ─────────────────────────────────────────────────────────────────────
// Copies text to clipboard. Tries the modern async API first; falls back to
// the legacy execCommand approach which works on localhost without permissions.
async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    try { await navigator.clipboard.writeText(text); return true } catch {}
  }
  const el = document.createElement('textarea')
  el.value = text
  el.style.cssText = 'position:fixed;opacity:0;top:0;left:0'
  document.body.appendChild(el)
  el.focus()
  el.select()
  const ok = document.execCommand('copy')
  document.body.removeChild(el)
  return ok
}

async function shareWatchlist(wl) {
  try {
    const res = await api.get(`/watchlist/${wl.id}/items`)
    const tickers = res.data.map(i => i.ticker).join(',')
    const url = `https://finance.yahoo.com/quotes/${tickers}/`
    const ok = await copyText(url)
    if (ok) {
      snackbarMsg.value = 'Yahoo Finance link copied!'
      snackbar.value = true
    } else {
      shareFallbackUrl.value = url
      shareFallback.value = true
    }
  } catch {
    snackbarMsg.value = 'Could not build share link'
    snackbar.value = true
  }
}

// ── Items ─────────────────────────────────────────────────────────────────────
async function fetchItems() {
  if (!selectedId.value) return
  loadingItems.value = true
  try {
    const res = await api.get(`/watchlist/${selectedId.value}/items`)
    items.value = res.data
  } catch { items.value = [] }
  finally { loadingItems.value = false }
}

async function addTickers() {
  const raw = tickerInput.value.trim()
  if (!raw || !selectedId.value) return
  const parsed = parseTickerString(raw)
  addingItems.value = true
  try {
    await api.post(`/watchlist/${selectedId.value}/items`, { tickers: parsed })
    tickerInput.value = ''
    await fetchItems()
    await fetchWatchlists()
  } catch { /* ignore */ }
  finally { addingItems.value = false }
}

async function removeItem(itemId) {
  try {
    await api.delete(`/watchlist/${selectedId.value}/items/${itemId}`)
    items.value = items.value.filter(i => i.id !== itemId)
    const wl = watchlists.value.find(w => w.id === selectedId.value)
    if (wl) wl.item_count = Math.max(0, wl.item_count - 1)
  } catch { /* ignore */ }
}

// Persist new item order emitted by WatchlistTable after drag. Also updates the
// local items array so a silent refresh doesn't snap back to the old order.
async function handleReorder(ids) {
  const lookup = Object.fromEntries(items.value.map(i => [i.id, i]))
  items.value = ids.map(id => lookup[id]).filter(Boolean)
  try {
    await api.put(`/watchlist/${selectedId.value}/items/reorder`, { ids })
  } catch { /* ignore — UI already reflects the reorder */ }
}

// ── Import shared watchlist ───────────────────────────────────────────────────
function openImport(tickersStr, nameStr) {
  importTickers.value = tickersStr
  importName.value    = nameStr || 'Shared Watchlist'
  importDest.value    = watchlists.value[0]?.id ?? null
  importDialog.value  = true
}

async function importSharedList() {
  const parsed = parseTickerString(importTickers.value)
  if (!parsed) return
  importingList.value = true
  try {
    let targetId = importDest.value
    if (!targetId) {
      // Create a new watchlist for the import
      const res = await api.post('/watchlist/', { name: importName.value })
      targetId = res.data.id
    }
    await api.post(`/watchlist/${targetId}/items`, { tickers: parsed })
    importDialog.value = false
    await fetchWatchlists()
    selectWatchlist(targetId)
  } catch { /* ignore */ }
  finally { importingList.value = false }
}

// ── Computed ──────────────────────────────────────────────────────────────────
const selectedWatchlist = computed(() => watchlists.value.find(w => w.id === selectedId.value))

// ── Mount: detect share URL params ───────────────────────────────────────────
// Silent background refresh — updates prices/P&L without showing the loading spinner.
async function silentRefreshItems() {
  if (!selectedId.value) return
  try {
    const res = await api.get(`/watchlist/${selectedId.value}/items`)
    items.value = res.data
  } catch { /* ignore auto-refresh errors */ }
}

let refreshTimer = null

onMounted(async () => {
  const tickers = route.query.tickers
  const name    = route.query.name
  await fetchWatchlists()
  if (tickers) {
    openImport(String(tickers), name ? String(name) : '')
    router.replace('/watchlist')
  }
  refreshTimer = setInterval(silentRefreshItems, 60_000)
})

onUnmounted(() => clearInterval(refreshTimer))
</script>

<template>
  <v-container fluid class="pa-6">

    <!-- Page header -->
    <v-row class="mb-4" align="center">
      <v-col cols="auto">
        <p class="text-h5 font-weight-bold">Watchlists</p>
        <p class="text-body-2 text-medium-emphasis">Track stocks without holding a position · drag rows to reorder · share via link</p>
      </v-col>
    </v-row>

    <v-row>

      <!-- ── Left panel ────────────────────────────────────────────────────── -->
      <v-col cols="12" md="3">
        <v-card rounded="lg" height="100%">
          <v-card-text class="pa-3">

            <v-btn block variant="tonal" color="primary" prepend-icon="mdi-plus" class="mb-3" @click="newDialog = true">
              New Watchlist
            </v-btn>

            <v-divider class="mb-2" />

            <div v-if="loadingLists" class="d-flex justify-center pa-4">
              <v-progress-circular indeterminate size="24" />
            </div>

            <v-list v-else density="compact" nav>
              <v-list-item
                v-for="wl in watchlists"
                :key="wl.id"
                :active="wl.id === selectedId"
                active-color="primary"
                rounded="lg"
                class="mb-1"
                @click="selectWatchlist(wl.id)"
              >
                <template #title>
                  <span class="text-body-2 font-weight-medium">{{ wl.name }}</span>
                </template>
                <template #subtitle>
                  <span class="text-caption text-medium-emphasis">{{ wl.item_count }} ticker{{ wl.item_count !== 1 ? 's' : '' }}</span>
                </template>
                <template #append>
                  <v-btn icon="mdi-share-variant-outline" size="x-small" variant="text" color="primary" @click.stop="shareWatchlist(wl)" />
                  <v-btn icon="mdi-pencil-outline"        size="x-small" variant="text" color="primary" @click.stop="openRename(wl)" />
                  <v-btn icon="mdi-delete-outline"        size="x-small" variant="text" color="error"   @click.stop="deleteWatchlist(wl.id)" />
                </template>
              </v-list-item>

              <div v-if="!watchlists.length" class="text-center pa-4">
                <v-icon size="32" color="surface-variant">mdi-star-outline</v-icon>
                <p class="text-caption text-medium-emphasis mt-2">No watchlists yet</p>
              </div>
            </v-list>

          </v-card-text>
        </v-card>
      </v-col>

      <!-- ── Right panel ───────────────────────────────────────────────────── -->
      <v-col cols="12" md="9">
        <v-card rounded="lg">
          <v-card-title class="pa-4 pb-2">
            <v-row align="center" no-gutters class="ga-3">
              <v-col cols="auto">
                <span class="text-body-1 font-weight-medium">
                  {{ selectedWatchlist ? selectedWatchlist.name : 'Select a watchlist' }}
                </span>
              </v-col>
              <v-col v-if="selectedId">
                <v-row no-gutters align="center" class="ga-2">
                  <v-col>
                    <v-text-field
                      v-model="tickerInput"
                      density="compact"
                      variant="outlined"
                      hide-details
                      placeholder="AAPL, MSFT, NVDA… or paste a Yahoo Finance / share URL"
                      :disabled="addingItems"
                      @keyup.enter="addTickers"
                    />
                  </v-col>
                  <v-col cols="auto">
                    <v-btn color="primary" variant="flat" :loading="addingItems" :disabled="!tickerInput.trim()" @click="addTickers">Add</v-btn>
                  </v-col>
                </v-row>
              </v-col>
            </v-row>
          </v-card-title>

          <v-card-text class="pa-0">
            <div v-if="!selectedId" class="text-center pa-12">
              <v-icon size="56" color="surface-variant">mdi-star-circle-outline</v-icon>
              <p class="text-body-1 text-medium-emphasis mt-4">Create or select a watchlist to get started</p>
            </div>

            <!-- :key resets WatchlistTable's internal search/filter/sort/expand when switching lists -->
            <WatchlistTable
              v-else
              :key="selectedId"
              :items="items"
              :loading="loadingItems"
              :can-reorder="true"
              :show-remove="true"
              @reorder="handleReorder"
              @remove="removeItem"
            />
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- ── Dialogs ─────────────────────────────────────────────────────────── -->

    <!-- New watchlist -->
    <v-dialog v-model="newDialog" max-width="360">
      <v-card rounded="lg">
        <v-card-title class="pa-4 pb-2">New Watchlist</v-card-title>
        <v-card-text class="pa-4 pt-2">
          <v-text-field v-model="newName" label="Watchlist name" variant="outlined" density="compact" autofocus hide-details @keyup.enter="createWatchlist" />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="newDialog = false; newName = ''">Cancel</v-btn>
          <v-btn color="primary" variant="flat" :loading="creatingList" :disabled="!newName.trim()" @click="createWatchlist">Create</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Rename watchlist -->
    <v-dialog v-model="renameDialog" max-width="360">
      <v-card rounded="lg">
        <v-card-title class="pa-4 pb-2">Rename Watchlist</v-card-title>
        <v-card-text class="pa-4 pt-2">
          <v-text-field v-model="renameName" label="New name" variant="outlined" density="compact" autofocus hide-details @keyup.enter="renameWatchlist" />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="renameDialog = false">Cancel</v-btn>
          <v-btn color="primary" variant="flat" :loading="renamingList" :disabled="!renameName.trim()" @click="renameWatchlist">Save</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Import shared watchlist -->
    <v-dialog v-model="importDialog" max-width="480">
      <v-card rounded="lg">
        <v-card-title class="pa-4 pb-2">
          <v-icon start color="primary">mdi-import</v-icon>
          Import Watchlist
        </v-card-title>
        <v-card-text class="pa-4 pt-2">
          <p class="text-body-2 text-medium-emphasis mb-3">
            Tickers to import: <strong>{{ importTickers }}</strong>
          </p>
          <v-select
            v-if="watchlists.length"
            v-model="importDest"
            :items="[{ title: '+ Create new watchlist', value: null }, ...watchlists.map(w => ({ title: w.name, value: w.id }))]"
            item-title="title"
            item-value="value"
            label="Add to watchlist"
            variant="outlined"
            density="compact"
            hide-details
            class="mb-3"
          />
          <v-text-field
            v-if="importDest === null"
            v-model="importName"
            label="New watchlist name"
            variant="outlined"
            density="compact"
            hide-details
          />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="importDialog = false">Skip</v-btn>
          <v-btn color="primary" variant="flat" :loading="importingList" @click="importSharedList">Import</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Share fallback: show URL when clipboard is blocked -->
    <v-dialog v-model="shareFallback" max-width="560">
      <v-card rounded="lg">
        <v-card-title class="pa-4 pb-2">
          <v-icon start color="primary">mdi-share-variant-outline</v-icon>
          Share Watchlist
        </v-card-title>
        <v-card-text class="pa-4 pt-1">
          <p class="text-body-2 text-medium-emphasis mb-3">Copy the link below and send it to anyone running this app:</p>
          <v-text-field
            :model-value="shareFallbackUrl"
            readonly
            variant="outlined"
            density="compact"
            hide-details
            @click="$event.target.select()"
          >
            <template #append-inner>
              <v-btn size="x-small" variant="tonal" color="primary" @click="copyText(shareFallbackUrl); shareFallback = false; snackbarMsg = 'Copied!'; snackbar = true">
                Copy
              </v-btn>
            </template>
          </v-text-field>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="shareFallback = false">Close</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar v-model="snackbar" timeout="3000" location="bottom right">
      {{ snackbarMsg }}
      <template #actions>
        <v-btn variant="text" @click="snackbar = false">OK</v-btn>
      </template>
    </v-snackbar>

  </v-container>
</template>
