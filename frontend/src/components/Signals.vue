<script setup>
defineProps({
  buy:       { type: Number, default: 0 },
  sell:      { type: Number, default: 0 },
  hold:      { type: Number, default: 0 },
  breakdown: { type: Object, default: () => ({}) },
})

const crossLabel = v => v === 'golden' ? 'Golden ✓' : v === 'death' ? 'Death ✗' : v
const crossColor = v => v === 'golden' ? 'success' : v === 'death' ? 'error' : 'default'
const trendColor = v => v === 'bullish' ? 'success' : v === 'bearish' ? 'error' : 'default'
const volColor   = v => v?.includes('bullish') ? 'success' : v?.includes('bearish') ? 'error' : 'default'
</script>

<template>
  <v-card rounded="lg">
    <v-card-title class="text-body-1 font-weight-medium pa-4 pb-2">
      <v-icon size="18" class="mr-2">mdi-signal-cellular-3</v-icon>
      Signal Engine
    </v-card-title>

    <v-card-text class="pa-4 pt-1">
      <!-- Progress bars -->
      <v-row align="center" no-gutters class="mb-1">
        <v-col cols="3" class="text-body-2 text-success font-weight-medium">Buy</v-col>
        <v-col cols="7"><v-progress-linear :model-value="buy" color="success" rounded height="10" /></v-col>
        <v-col cols="2" class="text-right text-caption text-success">{{ buy }}%</v-col>
      </v-row>
      <v-row align="center" no-gutters class="mb-1">
        <v-col cols="3" class="text-body-2 text-warning font-weight-medium">Hold</v-col>
        <v-col cols="7"><v-progress-linear :model-value="hold" color="warning" rounded height="10" /></v-col>
        <v-col cols="2" class="text-right text-caption text-warning">{{ hold }}%</v-col>
      </v-row>
      <v-row align="center" no-gutters class="mb-3">
        <v-col cols="3" class="text-body-2 text-error font-weight-medium">Sell</v-col>
        <v-col cols="7"><v-progress-linear :model-value="sell" color="error" rounded height="10" /></v-col>
        <v-col cols="2" class="text-right text-caption text-error">{{ sell }}%</v-col>
      </v-row>

      <v-divider class="mb-3" />

      <!-- Technical breakdown -->
      <p class="text-caption text-medium-emphasis mb-2 text-uppercase font-weight-medium">Technical</p>
      <v-row no-gutters class="mb-1" v-if="breakdown.price_vs_sma20">
        <v-col class="text-body-2">Price vs SMA-20</v-col>
        <v-col class="text-right">
          <v-chip size="x-small" :color="trendColor(breakdown.price_vs_sma20)" label>
            {{ breakdown.price_vs_sma20 }}
          </v-chip>
        </v-col>
      </v-row>
      <v-row no-gutters class="mb-1" v-if="breakdown.price_vs_sma50">
        <v-col class="text-body-2">Price vs SMA-50</v-col>
        <v-col class="text-right">
          <v-chip size="x-small" :color="trendColor(breakdown.price_vs_sma50)" label>
            {{ breakdown.price_vs_sma50 }}
          </v-chip>
        </v-col>
      </v-row>
      <v-row no-gutters class="mb-1" v-if="breakdown.sma_cross">
        <v-col class="text-body-2">SMA Cross</v-col>
        <v-col class="text-right">
          <v-chip size="x-small" :color="crossColor(breakdown.sma_cross)" label>
            {{ crossLabel(breakdown.sma_cross) }}
          </v-chip>
        </v-col>
      </v-row>
      <v-row no-gutters class="mb-3" v-if="breakdown.ema_cross">
        <v-col class="text-body-2">EMA Cross</v-col>
        <v-col class="text-right">
          <v-chip size="x-small" :color="crossColor(breakdown.ema_cross)" label>
            {{ crossLabel(breakdown.ema_cross) }}
          </v-chip>
        </v-col>
      </v-row>

      <!-- News sentiment breakdown -->
      <p class="text-caption text-medium-emphasis mb-2 text-uppercase font-weight-medium">News Sentiment</p>
      <v-row no-gutters class="mb-3">
        <v-col class="text-center">
          <v-chip size="small" color="success" variant="tonal" class="mr-1">
            <v-icon start size="12">mdi-thumb-up</v-icon>
            {{ breakdown.news_good ?? 0 }}
          </v-chip>
          <v-chip size="small" color="default" variant="tonal" class="mr-1">
            {{ breakdown.news_neutral ?? 0 }} neutral
          </v-chip>
          <v-chip size="small" color="error" variant="tonal">
            <v-icon start size="12">mdi-thumb-down</v-icon>
            {{ breakdown.news_bad ?? 0 }}
          </v-chip>
        </v-col>
      </v-row>

      <!-- Volume -->
      <p class="text-caption text-medium-emphasis mb-2 text-uppercase font-weight-medium">Volume</p>
      <v-row no-gutters class="mb-3" v-if="breakdown.volume">
        <v-col class="text-body-2">Signal</v-col>
        <v-col class="text-right">
          <v-chip size="x-small" :color="volColor(breakdown.volume)" label>
            {{ breakdown.volume.replace(/_/g, ' ') }}
          </v-chip>
        </v-col>
      </v-row>

      <!-- Composite score -->
      <v-divider class="mb-2" />
      <v-row no-gutters align="center">
        <v-col class="text-caption text-medium-emphasis">Composite Score</v-col>
        <v-col class="text-right text-body-2 font-weight-bold">{{ breakdown.composite }}/100</v-col>
      </v-row>
    </v-card-text>
  </v-card>
</template>
