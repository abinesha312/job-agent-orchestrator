<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { api } from './api'

const tabs = [
  { to: '/agents', label: 'Agents' },
  { to: '/history', label: 'History' },
  { to: '/evals', label: 'Evals' },
]
const info = ref('')
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
