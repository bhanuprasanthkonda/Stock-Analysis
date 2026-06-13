<script setup>
import { useRouter } from 'vue-router'

const props = defineProps({
  title:           { type: String, required: true },
  publisher:       { type: String, default: '' },
  url:             { type: String, default: '' },
  publishedAt:     { type: String, default: '' },
  sentiment:       { type: String, default: 'neutral' },
  compoundScore:   { type: Number, default: 0 },
  relatedTickers:  { type: Array, default: () => [] },
})

const router = useRouter()

const sentimentColor = s =>
  s === 'good' ? 'success' : s === 'bad' ? 'error' : 'default'

const sentimentIcon = s =>
  s === 'good' ? 'mdi-trending-up' : s === 'bad' ? 'mdi-trending-down' : 'mdi-minus'

const fmtTime = iso => {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function openTicker(ticker, e) {
  e.preventDefault()
  e.stopPropagation()
  router.push({ path: '/dashboard', query: { ticker } })
}
</script>

<template>
  <v-card
    variant="outlined"
    rounded="lg"
    class="mb-2"
    :href="url || undefined"
    :target="url ? '_blank' : undefined"
  >
    <v-card-text class="pa-3">
      <v-row no-gutters align="start">
        <v-col>
          <p class="text-body-2 font-weight-medium mb-1">{{ title }}</p>
          <v-row no-gutters align="center" class="mt-1">
            <p class="text-caption text-medium-emphasis mr-3">
              {{ publisher }}<span v-if="publisher && publishedAt"> · </span>{{ fmtTime(publishedAt) }}
            </p>
            <v-chip
              v-for="ticker in relatedTickers"
              :key="ticker"
              size="x-small"
              variant="tonal"
              color="primary"
              label
              class="mr-1"
              @click="openTicker(ticker, $event)"
            >
              {{ ticker }}
            </v-chip>
          </v-row>
        </v-col>
        <v-col cols="auto" class="ml-2 mt-1">
          <v-chip
            size="x-small"
            :color="sentimentColor(sentiment)"
            variant="tonal"
            label
          >
            <v-icon start size="10">{{ sentimentIcon(sentiment) }}</v-icon>
            {{ sentiment }}
          </v-chip>
        </v-col>
      </v-row>
    </v-card-text>
  </v-card>
</template>
