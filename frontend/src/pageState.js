import { ref } from 'vue'

// When set, Dashboard overrides the default Nasdaq-based page gradient.
// null = fall back to Nasdaq direction from the market bar.
// 'up' | 'down' = stock P&L direction for the currently viewed ticker.
export const pageGradientOverride = ref(null)
