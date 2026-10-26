<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from './api'
import { prefs } from './prefs'

const tabs = [
  { to: '/agents', label: 'Agents' },
  { to: '/history', label: 'History' },
  { to: '/evals', label: 'Evals' },
]
const info = ref('')
const initial = computed(() => (prefs.name.trim()[0] || 'P').toUpperCase())
const isDark = () =>
  prefs.theme === 'dark' || (prefs.theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
function toggleTheme() {
  prefs.theme = isDark() ? 'light' : 'dark'
}
const down = ref(false)
let timer: ReturnType<typeof setInterval> | undefined

async function ping() {
  try {
    const h = await api.health()
    info.value = `${h.storage} / ${h.embedder}`
    down.value = false
  } catch {
    down.value = true
  }
}
onMounted(() => {
  ping()
  timer = setInterval(ping, 10000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <header class="bar">
    <div class="bar-in">
      <strong class="logo">ApplyPilot</strong>
      <nav>
        <RouterLink v-for="t in tabs" :key="t.to" :to="t.to" class="tab">{{ t.label }}</RouterLink>
      </nav>
      <span class="pill" :class="down ? 'bad' : 'ok'" :title="info">{{ down ? 'API down' : 'API ok' }}</span>
      <button class="icon" :title="'Switch theme'" aria-label="Switch between light and dark theme" @click="toggleTheme">
        {{ isDark() ? 'Light' : 'Dark' }}
      </button>
      <RouterLink to="/profile" class="avatar" :title="prefs.name || 'Profile'" aria-label="Profile">{{ initial }}</RouterLink>
    </div>
  </header>
  <main class="page">
    <p v-if="down" class="notice bad">The API is not reachable. Start the backend and this page will recover.</p>
    <RouterView />
    <p class="muted foot">
      ApplyPilot drafts, you decide. It never applies and never sends email.
    </p>
  </main>
</template>

<style scoped>
.icon { padding: 4px 12px; font-size: 13px; }
.avatar { width: 30px; height: 30px; border-radius: 50%; background: var(--brand); color: var(--brand-ink);
  display: grid; place-items: center; font-weight: 700; text-decoration: none; }
.bar-in { flex-wrap: wrap; }
.bar { background: var(--panel); border-bottom: 1px solid var(--line); position: sticky; top: 0; z-index: 5; }
.bar-in { max-width: 1200px; margin: 0 auto; padding: 10px 20px; display: flex; gap: 24px; align-items: center; }
.logo { font-size: 16px; }
nav { display: flex; gap: 4px; flex: 1; flex-wrap: wrap; }
.tab { padding: 6px 14px; border-radius: 8px; text-decoration: none; color: var(--muted); font-weight: 600; }
.tab.router-link-active { background: var(--idle-bg); color: var(--ink); }
.page { max-width: 1200px; margin: 0 auto; padding: 20px; }
.page > * + * { margin-top: 16px; }
.foot { text-align: center; font-size: 12px; margin-top: 32px; }
</style>
