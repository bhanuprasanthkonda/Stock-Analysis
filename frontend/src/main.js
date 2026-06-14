import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import vuetify from './plugins/vuetify'
import App from './App.vue'
import Dashboard from './views/Dashboard.vue'
import Portfolio from './views/Portfolio.vue'
import History from './views/History.vue'
import News from './views/News.vue'
import Watchlist from './views/Watchlist.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', component: Dashboard },
    { path: '/portfolio', component: Portfolio },
    { path: '/watchlist', component: Watchlist },
    { path: '/history', component: History },
    { path: '/news', component: News },
  ],
})

createApp(App).use(vuetify).use(router).mount('#app')
