import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import './style.css'
import './prefs'
import AgentsView from './views/AgentsView.vue'
import EvalsView from './views/EvalsView.vue'
import HistoryView from './views/HistoryView.vue'
import ProfileView from './views/ProfileView.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/agents' },
    { path: '/agents', component: AgentsView, meta: { label: 'Agents' } },
    { path: '/history', component: HistoryView, meta: { label: 'History' } },
    { path: '/profile', component: ProfileView, meta: { label: 'Profile' } },
    { path: '/evals', component: EvalsView, meta: { label: 'Evals' } },
  ],
})

createApp(App).use(router).mount('#app')
