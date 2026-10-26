<script setup lang="ts">
import { computed } from 'vue'
import type { AgentCard } from '../types'
import { ago } from '../format'

const props = defineProps<{ agent: AgentCard; main?: boolean; selected?: boolean }>()
defineEmits<{ select: [id: string] }>()

const tone = computed(() => ({ idle: '', done: 'ok', error: 'bad' })[props.agent.state])
const label = computed(() => ({ idle: 'idle', done: 'ok', error: 'last task failed' })[props.agent.state])
</script>

<template>
  <article class="card panel" :class="{ main, selected }" @click="$emit('select', agent.id)">
    <div class="head">
      <h3>{{ agent.name }}</h3>
      <span class="pill" :class="tone">{{ label }}</span>
    </div>
    <p class="muted role">{{ agent.role }}</p>
    <div class="tools">
      <span v-for="t in agent.tools" :key="t" class="tool mono">{{ t }}</span>
    </div>
    <div class="stats">
      <div><b>{{ agent.tasks_total }}</b><span class="muted"> tasks</span></div>
      <div :class="{ bad: agent.tasks_failed }"><b>{{ agent.tasks_failed }}</b><span class="muted"> failed</span></div>
      <div class="muted">{{ ago(agent.last_run_at) }}</div>
    </div>
    <p v-if="agent.last_message" class="last mono" :title="agent.last_message">{{ agent.last_message }}</p>
    <ul v-if="agent.recent_tasks.length" class="tasks">
      <li v-for="t in agent.recent_tasks.slice(0, 4)" :key="t.id">
        <span class="dot" :class="t.ok ? 'ok' : 'bad'"></span>
        <span class="msg">{{ t.message }}</span>
        <span class="muted when">{{ ago(t.created_at) }}</span>
      </li>
    </ul>
    <p v-else class="muted empty">No tasks yet.</p>
  </article>
</template>

<style scoped>
.card { cursor: pointer; display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.card.selected { border-color: var(--brand); box-shadow: 0 0 0 1px var(--brand); }
.card.main { border-width: 2px; }
.head { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
.role { margin: 0; font-size: 13px; }
.tools { display: flex; flex-wrap: wrap; gap: 4px; }
.tool { background: var(--idle-bg); padding: 1px 7px; border-radius: 6px; }
.stats { display: flex; gap: 14px; align-items: baseline; flex-wrap: wrap; }
.stats .bad b { color: var(--bad); }
.last { margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); }
.tasks { list-style: none; padding: 0; margin: 0; border-top: 1px solid var(--line); }
.tasks li { display: flex; gap: 8px; align-items: baseline; padding: 4px 0; min-width: 0; }
.msg { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.when { font-size: 11px; white-space: nowrap; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); flex: none; }
.dot.ok { background: var(--ok); }
.dot.bad { background: var(--bad); }
.empty { margin: 0; font-size: 13px; }
</style>
