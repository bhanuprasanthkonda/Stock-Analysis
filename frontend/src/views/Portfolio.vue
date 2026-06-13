<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()

// ── State ─────────────────────────────────────────────────────────────────────
const positions = ref([])
const loadingPositions = ref(false)
const snackbar = ref({ show: false, text: '', color: 'success' })

function notify(text, color = 'success') {
  snackbar.value = { show: true, text, color }
}

async function fetchPositions() {
  loadingPositions.value = true
  try {
    const res = await api.get('/portfolio/positions')
    positions.value = res.data
  } catch { notify('Failed to load portfolio', 'error') }
  finally { loadingPositions.value = false }
}

onMounted(fetchPositions)

function goToDashboard(ticker) {
  router.push({ path: '/dashboard', query: { ticker } })
}

// ── Add position dialog ───────────────────────────────────────────────────────
const dialog = ref(false)
const saving = ref(false)
const lookingUp = ref(false)
const form = ref({ ticker: '', company_name: '', shares: null, buy_price: null, notes: '' })
const formRef = ref(null)

function openDialog() {
  form.value = { ticker: '', company_name: '', shares: null, buy_price: null, notes: '' }
  dialog.value = true
}

async function lookupTicker() {
  const sym = form.value.ticker.trim().toUpperCase()
  if (!sym) return
  form.value.ticker = sym
  lookingUp.value = true
  form.value.company_name = ''
  try {
    const res = await api.get(`/stocks/${sym}?period=1d&interval=1d`)
    form.value.company_name = res.data.company_name ?? ''
  } catch {}
  finally { lookingUp.value = false }
}

async function savePosition() {
  const { valid } = await formRef.value.validate()
  if (!valid) return
  saving.value = true
  try {
    await api.post('/portfolio/', {
      ticker: form.value.ticker.toUpperCase(),
      company_name: form.value.company_name || null,
      shares: Number(form.value.shares),
      buy_price: Number(form.value.buy_price),
      notes: form.value.notes || null,
    })
    dialog.value = false
    notify('Position added')
    fetchPositions()
  } catch (e) {
    notify(e.response?.data?.detail ?? 'Failed to add position', 'error')
  } finally { saving.value = false }
}

async function deletePosition(id) {
  try {
    await api.delete(`/portfolio/${id}`)
    notify('Position removed')
    fetchPositions()
  } catch { notify('Failed to delete position', 'error') }
}

// ── Edit position dialog ──────────────────────────────────────────────────────
const editDialog = ref(false)
const editSaving = ref(false)
const editForm = ref({ id: null, ticker: '', company_name: '', shares: null, buy_price: null, notes: '' })
const editFormRef = ref(null)

function openEditDialog(item) {
  editForm.value = {
    id: item.id,
    ticker: item.ticker,
    company_name: item.company_name ?? '',
    shares: item.shares,
    buy_price: item.buy_price,
    notes: item.notes ?? '',
  }
  editDialog.value = true
}

async function saveEdit() {
  const { valid } = await editFormRef.value.validate()
  if (!valid) return
  editSaving.value = true
  try {
    await api.put(`/portfolio/${editForm.value.id}`, {
      shares: Number(editForm.value.shares),
      buy_price: Number(editForm.value.buy_price),
      notes: editForm.value.notes || null,
    })
    editDialog.value = false
    notify('Position updated')
    fetchPositions()
  } catch (e) {
    notify(e.response?.data?.detail ?? 'Failed to update position', 'error')
  } finally { editSaving.value = false }
}

// ── Table headers ─────────────────────────────────────────────────────────────
const positionHeaders = [
  { title: 'Ticker',    key: 'ticker' },
  { title: 'Company',   key: 'company_name' },
  { title: 'Shares',    key: 'shares' },
  { title: 'Avg Cost',  key: 'buy_price' },
  { title: 'Cur Price', key: 'current_price' },
  { title: 'Mkt Value', key: 'market_value' },
  { title: 'P&L $',     key: 'pnl_dollar' },
  { title: 'P&L %',     key: 'pnl_pct' },
  { title: '',          key: 'actions', sortable: false, align: 'end' },
]

const fmtPrice  = v => v != null ? `$${Number(v).toFixed(2)}` : '—'
const fmtPnl    = v => v != null ? `${v >= 0 ? '+' : '-'}$${Math.abs(Number(v)).toFixed(2)}` : '—'
const fmtPnlPct = v => v != null ? `${v >= 0 ? '+' : ''}${Number(v).toFixed(2)}%` : '—'
const pnlColor  = v => v == null ? '' : v >= 0 ? 'text-success' : 'text-error'
</script>

<template>
  <v-container fluid class="pa-6">

    <v-card rounded="lg">
      <v-card-title class="pa-4 pb-2">
        <v-row align="center" no-gutters>
          <v-col>
            <span class="text-body-1 font-weight-medium">
              <v-icon size="18" class="mr-2">mdi-briefcase-outline</v-icon>
              My Portfolio
            </span>
            <span v-if="loadingPositions" class="text-caption text-medium-emphasis ml-3">
              <v-progress-circular size="12" width="2" indeterminate class="mr-1" />
              Fetching live prices…
            </span>
          </v-col>
          <v-col class="text-right">
            <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-plus" @click="openDialog">
              Add Position
            </v-btn>
          </v-col>
        </v-row>
      </v-card-title>

      <v-data-table
        :items="positions"
        :headers="positionHeaders"
        :loading="loadingPositions"
        density="comfortable"
        no-data-text="No positions yet — add one above"
      >
        <template #item.ticker="{ item }">
          <v-btn
            variant="text"
            size="small"
            color="primary"
            class="font-weight-bold px-1"
            @click="goToDashboard(item.ticker)"
          >
            {{ item.ticker }}
          </v-btn>
        </template>
        <template #item.shares="{ item }">
          {{ Number(item.shares).toLocaleString() }}
        </template>
        <template #item.buy_price="{ item }">
          {{ fmtPrice(item.buy_price) }}
        </template>
        <template #item.current_price="{ item }">
          {{ fmtPrice(item.current_price) }}
        </template>
        <template #item.market_value="{ item }">
          {{ fmtPrice(item.market_value) }}
        </template>
        <template #item.pnl_dollar="{ item }">
          <span :class="pnlColor(item.pnl_dollar)" class="font-weight-medium">
            {{ fmtPnl(item.pnl_dollar) }}
          </span>
        </template>
        <template #item.pnl_pct="{ item }">
          <v-chip
            v-if="item.pnl_pct != null"
            size="x-small"
            :color="item.pnl_pct >= 0 ? 'success' : 'error'"
            variant="tonal"
          >
            {{ fmtPnlPct(item.pnl_pct) }}
          </v-chip>
          <span v-else>—</span>
        </template>
        <template #item.actions="{ item }">
          <v-btn
            icon="mdi-pencil-outline"
            size="x-small"
            variant="text"
            color="primary"
            class="mr-1"
            @click="openEditDialog(item)"
          />
          <v-btn
            icon="mdi-trash-can-outline"
            size="x-small"
            variant="text"
            color="error"
            @click="deletePosition(item.id)"
          />
        </template>
      </v-data-table>
    </v-card>

    <!-- Edit Position Dialog -->
    <v-dialog v-model="editDialog" max-width="440" persistent>
      <v-card rounded="lg">
        <v-card-title class="pa-5 pb-2 text-body-1 font-weight-medium">
          Edit Position — {{ editForm.ticker }}
          <span class="text-medium-emphasis text-caption ml-2">{{ editForm.company_name }}</span>
        </v-card-title>
        <v-card-text class="pa-5 pt-2">
          <v-form ref="editFormRef">
            <v-row dense>
              <v-col cols="6">
                <v-text-field
                  v-model="editForm.shares"
                  label="Shares *"
                  type="number"
                  variant="outlined"
                  density="compact"
                  :rules="[v => (!!v && v > 0) || 'Must be > 0']"
                />
              </v-col>
              <v-col cols="6">
                <v-text-field
                  v-model="editForm.buy_price"
                  label="Buy Price (USD) *"
                  type="number"
                  variant="outlined"
                  density="compact"
                  :rules="[v => (!!v && v > 0) || 'Must be > 0']"
                />
              </v-col>
              <v-col cols="12">
                <v-text-field
                  v-model="editForm.notes"
                  label="Notes"
                  variant="outlined"
                  density="compact"
                />
              </v-col>
            </v-row>
          </v-form>
        </v-card-text>
        <v-card-actions class="pa-5 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="editDialog = false">Cancel</v-btn>
          <v-btn color="primary" variant="tonal" :loading="editSaving" @click="saveEdit">Save</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Add Position Dialog -->
    <v-dialog v-model="dialog" max-width="520" persistent>
      <v-card rounded="lg">
        <v-card-title class="pa-5 pb-2 text-body-1 font-weight-medium">Add Position</v-card-title>
        <v-card-text class="pa-5 pt-2">
          <v-form ref="formRef">
            <v-row dense>
              <v-col cols="6">
                <v-text-field
                  v-model="form.ticker"
                  label="Ticker *"
                  variant="outlined"
                  density="compact"
                  :rules="[v => !!v || 'Required']"
                  @blur="lookupTicker"
                />
              </v-col>
              <v-col cols="6">
                <v-text-field
                  v-model="form.company_name"
                  label="Company Name"
                  variant="outlined"
                  density="compact"
                  readonly
                  :loading="lookingUp"
                  placeholder="auto-filled from ticker"
                />
              </v-col>
              <v-col cols="6">
                <v-text-field
                  v-model="form.shares"
                  label="Shares *"
                  type="number"
                  variant="outlined"
                  density="compact"
                  :rules="[v => (!!v && v > 0) || 'Must be > 0']"
                />
              </v-col>
              <v-col cols="6">
                <v-text-field
                  v-model="form.buy_price"
                  label="Buy Price (USD) *"
                  type="number"
                  variant="outlined"
                  density="compact"
                  :rules="[v => (!!v && v > 0) || 'Must be > 0']"
                />
              </v-col>
              <v-col cols="12">
                <v-text-field
                  v-model="form.notes"
                  label="Notes"
                  variant="outlined"
                  density="compact"
                />
              </v-col>
            </v-row>
          </v-form>
        </v-card-text>
        <v-card-actions class="pa-5 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="dialog = false">Cancel</v-btn>
          <v-btn color="primary" variant="tonal" :loading="saving" @click="savePosition">Save</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" timeout="3000" location="bottom right">
      {{ snackbar.text }}
    </v-snackbar>

  </v-container>
</template>
