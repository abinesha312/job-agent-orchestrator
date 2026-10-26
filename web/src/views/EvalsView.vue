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
type Tab = 'dashboard' | 'suites' | 'results' | 'history'
const tab = ref<Tab>('dashboard')
const tabs: { id: Tab; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'suites', label: 'Suites' },
  { id: 'results', label: 'Results' },
  { id: 'history', label: 'History' },
]

// newest run per suite; oldest first for the trend line
const chrono = computed(() => [...history.value].sort((a, b) => a.started_at.localeCompare(b.started_at)))
const latest = computed(() => {
  const m = new Map<string, Omit<EvalRun, 'cases'>>()
  for (const r of chrono.value) m.set(r.suite, r)
  return [...m.values()]
})
const ran = computed(() => latest.value.filter((r) => r.status !== 'skipped'))
const kpi = computed(() => {
  const total = ran.value.reduce((a, r) => a + r.total, 0)
  const passed = ran.value.reduce((a, r) => a + r.passed, 0)
  return {
    suites: ran.value.length,
    passing: ran.value.filter((r) => r.status === 'passed').length,
    skipped: latest.value.length - ran.value.length,
    total,
    passed,
    rate: total ? passed / total : null,
  }
})
const metricAvg = computed(() => {
  const acc: Record<string, number[]> = {}
  for (const r of ran.value) for (const [k, v] of Object.entries(r.summary)) if (v !== null) (acc[k] ??= []).push(v)
  return Object.entries(acc).map(([k, vs]) => ({ k, v: vs.reduce((a, b) => a + b, 0) / vs.length }))
})
const trend = computed(() => {
  const pts = chrono.value.filter((r) => r.total > 0).map((r) => r.passed / r.total)
  const W = 320
  const H = 90
  const xs = (i: number) => (pts.length < 2 ? W / 2 : 8 + (i * (W - 16)) / (pts.length - 1))
  const ys = (v: number) => H - 8 - v * (H - 16)
  return { pts, W, H, line: pts.map((v, i) => `${xs(i)},${ys(v)}`).join(' '), xs, ys }
})

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

    <nav class="subtabs" role="tablist">
      <button v-for="t in tabs" :key="t.id" role="tab" :aria-selected="tab === t.id" :class="{ on: tab === t.id }" @click="tab = t.id">{{ t.label }}</button>
    </nav>

    <template v-if="tab === 'dashboard'">
      <p v-if="!latest.length" class="panel muted">No runs yet. Use Run all suites, then come back here.</p>
      <template v-else>
        <div class="tiles">
          <div class="panel tile"><span class="muted small">Cases passed</span><b>{{ pct(kpi.rate) }}</b><span class="muted small">{{ kpi.passed }} of {{ kpi.total }}</span></div>
          <div class="panel tile"><span class="muted small">Suites passing</span><b>{{ kpi.passing }}/{{ kpi.suites }}</b><span class="muted small">{{ kpi.skipped }} skipped</span></div>
          <div class="panel tile"><span class="muted small">Runs recorded</span><b>{{ history.length }}</b><span class="muted small">this session</span></div>
          <div class="panel tile"><span class="muted small">Last run</span><b>{{ ago(chrono[chrono.length - 1].started_at) }}</b><span class="muted small">{{ chrono[chrono.length - 1].name }}</span></div>
        </div>
        <div class="charts">
          <div class="panel">
            <h3>Pass rate by suite</h3>
            <div v-for="r in latest" :key="r.id" class="meter">
              <span class="mname">{{ r.name }}</span>
              <span class="bar"><span class="fill" :class="r.status === 'failed' ? 'bad' : 'ok'" :style="{ width: (r.total ? (r.passed / r.total) * 100 : 0) + '%' }"></span></span>
              <span class="mval">{{ r.status === 'skipped' ? 'skip' : pct(r.total ? r.passed / r.total : null) }}</span>
            </div>
          </div>
          <div class="panel">
            <h3>Average score by metric</h3>
            <div v-for="m in metricAvg" :key="m.k" class="meter">
              <span class="mname">{{ m.k }}</span>
              <span class="bar">
                <span class="fill" :class="metricOk(m.k, m.v) ? 'ok' : 'bad'" :style="{ width: m.v * 100 + '%' }"></span>
                <span v-if="threshold(m.k) !== undefined" class="tick" :style="{ left: (threshold(m.k) ?? 0) * 100 + '%' }"></span>
              </span>
              <span class="mval">{{ pct(m.v) }}</span>
            </div>
            <p class="muted small">Vertical mark = threshold.</p>
          </div>
          <div class="panel">
            <h3>Pass rate over runs</h3>
            <p v-if="trend.pts.length < 2" class="muted small">Run suites more than once to see a trend.</p>
            <svg v-else :viewBox="`0 0 ${trend.W} ${trend.H}`" class="spark" role="img" aria-label="Pass rate per run">
              <line x1="8" :x2="trend.W - 8" :y1="trend.ys(1)" :y2="trend.ys(1)" class="grid" />
              <line x1="8" :x2="trend.W - 8" :y1="trend.ys(0)" :y2="trend.ys(0)" class="grid" />
              <polyline :points="trend.line" class="trendline" />
              <circle v-for="(v, i) in trend.pts" :key="i" :cx="trend.xs(i)" :cy="trend.ys(v)" r="3" class="dot" />
            </svg>
          </div>
        </div>
        <div class="panel">
          <h3>Latest result per suite</h3>
          <div class="scroll-x">
            <table>
              <thead><tr><th>Suite</th><th>Status</th><th>Passed</th><th>Failed</th><th>Duration</th><th>When</th></tr></thead>
              <tbody>
                <tr v-for="r in latest" :key="r.id">
                  <td>{{ r.name }}</td>
                  <td><span class="pill" :class="tone(r.status)">{{ r.status }}</span></td>
                  <td>{{ r.passed }}/{{ r.total }}</td><td>{{ r.failed }}</td>
                  <td>{{ r.duration_ms }} ms</td><td class="muted">{{ ago(r.started_at) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
    </template>

    <div v-if="catalog && tab === 'suites'" class="panel row">
      <b>Engines</b>
      <span v-for="e in catalog.engines" :key="e.id" class="engine">
        <span class="pill" :class="e.available ? 'ok' : ''">{{ e.name }}</span>
        <span v-if="!e.available" class="muted small">{{ e.reason }}</span>
      </span>
    </div>

    <div v-if="catalog && tab === 'suites'" class="suites">
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
          <button v-if="results[s.id]?.cases.length" @click="open = results[s.id]; tab = 'results'">Details</button>
        </div>
      </article>
    </div>

    <p v-if="tab === 'results' && !open" class="panel muted">Run a suite or open one from History to see its cases.</p>
    <div v-if="tab === 'results' && open" class="panel">
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

    <div v-if="catalog && tab === 'results'" class="panel">
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

    <div v-if="tab === 'history'" class="panel">
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
              <td><button @click="show(h.id); tab = 'results'">Open</button></td>
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
.subtabs { display: flex; gap: 4px; border-bottom: 1px solid var(--line); }
.subtabs button { border: 0; background: none; padding: 8px 14px; cursor: pointer; color: var(--muted); font: inherit;
  border-bottom: 2px solid transparent; margin-bottom: -1px; border-radius: 0; }
.subtabs button.on { color: var(--ink); border-bottom-color: var(--brand); font-weight: 600; }
.tiles { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); }
.tile { display: flex; flex-direction: column; gap: 2px; }
.tile b { font-size: 26px; }
.charts { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
.bar { position: relative; }
.tick { position: absolute; top: -2px; bottom: -2px; width: 2px; background: var(--ink); opacity: .6; }
.spark { width: 100%; height: auto; }
.grid { stroke: var(--line); stroke-width: 1; }
.trendline { fill: none; stroke: var(--brand); stroke-width: 2; }
.dot { fill: var(--brand); }
.inline { display: inline-flex; gap: 6px; align-items: center; margin: 0; }
.inline input { width: auto; }
</style>
