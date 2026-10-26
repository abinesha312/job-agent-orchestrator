<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { ago, pct } from '../format'
import type { EvalCatalog, EvalRun } from '../types'

const catalog = ref<EvalCatalog | null>(null)
const results = ref<Record<string, EvalRun>>({})
const history = ref<Omit<EvalRun, 'cases'>[]>([])
const open = ref<EvalRun | null>(null)
const running = ref<string[]>([])
const error = ref('')
const sample = ref(5)
const onlyFailed = ref(false)

const metricCols = computed(() => {
  const keys: string[] = []
  for (const c of open.value?.cases ?? []) for (const k of Object.keys(c.scores)) if (!keys.includes(k)) keys.push(k)
  return keys
})
const rows = computed(() => (open.value?.cases ?? []).filter((c) => !onlyFailed.value || !c.passed))

function threshold(metric: string): number | undefined {
  return catalog.value?.thresholds[metric]
}
function metricOk(metric: string, v: number | null | undefined): boolean {
  const t = threshold(metric)
  if (v === null || v === undefined) return true
  return t === undefined ? v >= 1 : v >= t
}

async function loadHistory() {
  history.value = (await api.evalRuns()).runs
}

async function run(id: string) {
  running.value.push(id)
  error.value = ''
  try {
    const r = await api.evalRun(id, sample.value)
    results.value[id] = r
    open.value = r
    await loadHistory()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    running.value = running.value.filter((x) => x !== id)
  }
}

async function runAll() {
  for (const s of catalog.value?.suites ?? []) await run(s.id)
}

async function show(id: string) {
  try {
    open.value = await api.evalRunGet(id)
  } catch (e) {
    error.value = (e as Error).message
  }
}

const tone = (s: string) => (s === 'passed' ? 'ok' : s === 'failed' ? 'bad' : '')

onMounted(async () => {
  try {
    catalog.value = await api.evalCatalog()
    await loadHistory()
  } catch (e) {
    error.value = (e as Error).message
  }
})
</script>

<template>
  <section class="stack">
    <div class="panel row">
      <div class="grow">
        <h2>Evaluation</h2>
        <p class="muted">
          Retrieval and generation are scored with the RAGAS metric definitions, offline. The RAGAS and DeepEval
          suites run the real libraries when installed and configured.
        </p>
      </div>
      <div style="width: 110px"><label>LLM sample</label><input v-model.number="sample" type="number" min="1" max="20" /></div>
      <button class="primary" :disabled="running.length > 0 || !catalog" @click="runAll">Run all suites</button>
    </div>

    <p v-if="error" class="notice bad">{{ error }}</p>

    <div v-if="catalog" class="panel row">
      <b>Engines</b>
      <span v-for="e in catalog.engines" :key="e.id" class="engine">
        <span class="pill" :class="e.available ? 'ok' : ''">{{ e.name }}</span>
        <span v-if="!e.available" class="muted small">{{ e.reason }}</span>
      </span>
    </div>

    <div v-if="catalog" class="suites">
      <article v-for="s in catalog.suites" :key="s.id" class="panel suite">
        <div class="row between">
          <h3>{{ s.name }}</h3>
          <span v-if="results[s.id]" class="pill" :class="tone(results[s.id].status)">{{ results[s.id].status }}</span>
        </div>
        <p class="muted small">{{ s.about }}</p>
        <p class="mono muted">{{ s.engine }}</p>
        <div v-if="results[s.id]?.total" class="muted small">
          {{ results[s.id].passed }}/{{ results[s.id].total }} cases in {{ results[s.id].duration_ms }} ms
        </div>
        <div v-if="results[s.id]">
          <div v-for="(v, k) in results[s.id].summary" :key="k" class="meter">
            <span class="mname">{{ k }}</span>
            <span class="bar"><span class="fill" :class="metricOk(String(k), v) ? 'ok' : 'bad'" :style="{ width: (v ?? 0) * 100 + '%' }"></span></span>
            <span class="mval">{{ pct(v) }}</span>
          </div>
          <p v-if="results[s.id].notes" class="muted small">{{ results[s.id].notes }}</p>
        </div>
        <div class="row">
          <button :disabled="running.includes(s.id)" @click="run(s.id)">{{ running.includes(s.id) ? 'Running...' : 'Run' }}</button>
          <button v-if="results[s.id]?.cases.length" @click="open = results[s.id]">Details</button>
        </div>
      </article>
    </div>

    <div v-if="open" class="panel">
      <div class="row">
        <h3 class="grow">{{ open.name }} <span class="pill" :class="tone(open.status)">{{ open.status }}</span></h3>
        <label class="inline"><input v-model="onlyFailed" type="checkbox" /> failed only</label>
      </div>
      <p v-if="open.notes" class="notice">{{ open.notes }}</p>
      <p v-if="!open.cases.length" class="muted">No cases ran.</p>
      <div v-else class="scroll-x">
        <table>
          <thead>
            <tr>
              <th>Case</th>
              <th v-for="m in metricCols" :key="m">{{ m }}<span v-if="threshold(m) !== undefined" class="muted"> &ge;{{ pct(threshold(m)) }}</span></th>
              <th>Result</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in rows" :key="c.id">
              <td class="mono">{{ c.id }}</td>
              <td v-for="m in metricCols" :key="m">
                <span v-if="c.scores[m] !== undefined" :class="metricOk(m, c.scores[m]) ? 'okc' : 'badc'">{{ pct(c.scores[m]) }}</span>
              </td>
              <td><span class="pill" :class="c.passed ? 'ok' : 'bad'">{{ c.passed ? 'pass' : 'fail' }}</span></td>
              <td class="muted small">{{ c.notes }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="catalog" class="panel">
      <h3>Gate definitions</h3>
      <div class="scroll-x">
        <table>
          <thead><tr><th>Gate</th><th>What it checks</th><th>Threshold</th><th>Hard fail</th></tr></thead>
          <tbody>
            <tr v-for="g in catalog.gates" :key="g.name">
              <td>{{ g.name }}</td><td>{{ g.checks }}</td>
              <td>{{ g.threshold === null ? 'pass/fail' : pct(g.threshold) }}</td>
              <td>{{ g.hard_fail ? 'yes' : '' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="panel">
      <h3>History</h3>
      <p v-if="!history.length" class="muted">No runs yet.</p>
      <div v-else class="scroll-x">
        <table>
          <thead><tr><th>Suite</th><th>Status</th><th>Cases</th><th>When</th><th></th></tr></thead>
          <tbody>
            <tr v-for="h in history" :key="h.id">
              <td>{{ h.name }}</td>
              <td><span class="pill" :class="tone(h.status)">{{ h.status }}</span></td>
              <td>{{ h.passed }}/{{ h.total }}</td>
              <td class="muted">{{ ago(h.started_at) }}</td>
              <td><button @click="show(h.id)">Open</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>

<style scoped>
.grow { flex: 1; min-width: 220px; }
.between { justify-content: space-between; }
.small { font-size: 12px; margin: 0; }
.suites { display: grid; gap: 14px; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); }
.suite { display: flex; flex-direction: column; gap: 8px; }
.engine { display: inline-flex; gap: 6px; align-items: center; }
.meter { display: grid; grid-template-columns: 130px 1fr 44px; gap: 8px; align-items: center; margin: 3px 0; font-size: 12px; }
.mname { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mval { text-align: right; }
.bar { height: 8px; background: var(--idle-bg); border-radius: 4px; overflow: hidden; }
.fill { display: block; height: 100%; }
.fill.ok { background: var(--ok); }
.fill.bad { background: var(--bad); }
.okc { color: var(--ok); font-weight: 600; }
.badc { color: var(--bad); font-weight: 600; }
.inline { display: inline-flex; gap: 6px; align-items: center; margin: 0; }
.inline input { width: auto; }
</style>
