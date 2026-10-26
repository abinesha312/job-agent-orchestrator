import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import './style.css'
import AgentsView from './views/AgentsView.vue'
import ResumeView from './views/ResumeView.vue'
import JobsView from './views/JobsView.vue'
import ReviewView from './views/ReviewView.vue'
import EvalsView from './views/EvalsView.vue'
import HistoryView from './views/HistoryView.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/agents' },
    { path: '/agents', component: AgentsView, meta: { label: 'Agents' } },
    { path: '/resume', component: ResumeView, meta: { label: 'Resume' } },
    { path: '/jobs', component: JobsView, meta: { label: 'Jobs' } },
    { path: '/review', component: ReviewView, meta: { label: 'Review' } },
    { path: '/history', component: HistoryView, meta: { label: 'History' } },
    { path: '/evals', component: EvalsView, meta: { label: 'Evals' } },
  ],
})

createApp(App).use(router).mount('#app')
