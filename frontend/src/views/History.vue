<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()
const history = ref([])
const loading = ref(false)

async function fetchHistory() {
  loading.value = true
  try {
    const res = await api.get('/portfolio/history')
    history.value = res.data
  } catch {}
  finally { loading.value = false }
}

onMounted(fetchHistory)

function goToDashboard(ticker) {
  router.push({ path: '/dashboard', query: { ticker } })
}

const headers = [
  { title: 'Ticker',      key: 'ticker' },
  { title: 'Company',     key: 'company_name' },
  { title: 'Searched At', key: 'searched_at' },
  { title: '',            key: 'actions', sortable: false, align: 'end' },
]

const fmtDate = iso => iso ? new Date(iso).toLocaleString() : '—'
</script>

<template>
  <v-container fluid class="pa-6">
    <v-card rounded="lg">
      <v-card-title class="pa-4 pb-2 text-body-1 font-weight-medium">
        <v-icon size="18" class="mr-2">mdi-history</v-icon>
        Search History
      </v-card-title>
      <v-data-table
        :items="history"
        :headers="headers"
        :loading="loading"
        density="comfortable"
        no-data-text="No search history yet — search a ticker on the Dashboard"
      >
        <template #item.ticker="{ item }">
          <v-btn variant="text" size="small" color="primary" class="font-weight-bold px-1" @click="goToDashboard(item.ticker)">
            {{ item.ticker }}
          </v-btn>
        </template>
        <template #item.searched_at="{ item }">
          {{ fmtDate(item.searched_at) }}
        </template>
        <template #item.actions="{ item }">
          <v-btn variant="text" size="x-small" color="primary" prepend-icon="mdi-open-in-app" @click="goToDashboard(item.ticker)">
            View
          </v-btn>
        </template>
      </v-data-table>
    </v-card>
  </v-container>
</template>
