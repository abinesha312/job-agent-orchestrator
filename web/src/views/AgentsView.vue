<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api'
import { clock } from '../format'
import AgentCardView from '../components/AgentCardView.vue'
import type { AgentsOverview, Task } from '../types'

const data = ref<AgentsOverview | null>(null)
const events = ref<Task[]>([])
const error = ref('')
const filter = ref('')
let timer: ReturnType<typeof setInterval> | undefined

async function refresh() {
  try {
    const [a, t] = await Promise.all([api.agents(), api.timeline()])
    data.value = a
    events.value = t.events
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
  }
}

function pick(id: string) {
  filter.value = filter.value === id ? '' : id
}

const shown = computed(() => {
  const rows = filter.value ? events.value.filter((e) => e.agent === filter.value) : events.value
  return [...rows].reverse().slice(0, 80)
})

const flow = computed(() => data.value?.subagents.map((s) => s.name) ?? [])

onMounted(() => {
  refresh()
  timer = setInterval(refresh, 3000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <section class="stack">
    <div class="panel row top">
      <div class="grow">
        <h2>Agent workflow</h2>
        <p class="muted">
          The main agent drives each job through its subagents and stops at your approval. Every task they run is logged here and scored in Evals.
          {{ data ? `${data.total_tasks} tasks logged.` : '' }}
        </p>
      </div>
    </div>

    <p v-if="error" class="notice bad">{{ error }}</p>

    <template v-if="data">
      <div class="tree">
        <div class="main-wrap">
          <AgentCardView :agent="data.main" main :selected="filter === data.main.id" @select="pick" />
        </div>
        <div class="trunk"></div>
        <div class="subs">
          <AgentCardView
            v-for="s in data.subagents" :key="s.id" :agent="s"
            :selected="filter === s.id" @select="pick"
          />
        </div>
      </div>
      <p class="muted flow">Flow: {{ flow.join('  >  ') }}</p>
    </template>
    <p v-else-if="!error" class="muted">Loading...</p>

    <div class="panel">
      <div class="row">
        <h3 class="grow">Activity {{ filter ? `(${filter})` : '' }}</h3>
        <button v-if="filter" @click="filter = ''">Show all</button>
      </div>
      <p v-if="!shown.length" class="muted">Nothing yet. Upload a resume, add jobs, then run the pipeline.</p>
      <div v-else class="scroll-x">
        <table>
          <thead><tr><th>Time</th><th>Agent</th><th></th><th>Task</th><th>Job</th><th>ms</th></tr></thead>
          <tbody>
            <tr v-for="e in shown" :key="e.id">
              <td class="mono">{{ clock(e.created_at) }}</td>
              <td>{{ e.agent }}</td>
              <td><span class="pill" :class="e.ok ? 'ok' : 'bad'">{{ e.ok ? 'ok' : 'fail' }}</span></td>
              <td>{{ e.message }}</td>
              <td class="mono muted">{{ e.job_id ? e.job_id.slice(0, 8) : '' }}</td>
              <td class="mono muted">{{ e.detail?.duration_ms ?? '' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>

<style scoped>
.top { justify-content: space-between; }
.grow { flex: 1; min-width: 220px; }
.tree { display: flex; flex-direction: column; align-items: stretch; }
.main-wrap { max-width: 560px; width: 100%; margin: 0 auto; }
.trunk { width: 2px; height: 22px; background: var(--line); margin: 0 auto; }
.subs {
  display: grid; gap: 14px; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  position: relative; padding-top: 14px; border-top: 2px solid var(--line);
}
.flow { font-size: 12px; margin: 0; }
</style>
