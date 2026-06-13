<script setup>
import { ref } from 'vue'

const drawer = ref(true)
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
      <v-app-bar-title class="text-body-1 font-weight-medium">
        Local Stock Analyzer
      </v-app-bar-title>
    </v-app-bar>

    <v-main>
      <router-view />
    </v-main>
  </v-app>
</template>
