<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import type { HistoryDetail, HistoryRow, HistorySummary } from '../types'

const summary = ref<HistorySummary | null>(null)
const rows = ref<HistoryRow[]>([])
const total = ref(0)
const detail = ref<HistoryDetail | null>(null)
const error = ref('')
const msg = ref('')
const loading = ref(false)

const company = ref('')
const status = ref('')
const q = ref('')
const page = ref(0)
const size = 25

const pages = computed(() => Math.max(1, Math.ceil(total.value / size)))
const statuses = computed(() => Object.entries(summary.value?.by_status ?? {}))
const maxStatus = computed(() => Math.max(1, ...statuses.value.map(([, n]) => n)))

const tone = (s: string | null) =>
  s === 'confirmed' || s === 'interviewing' ? 'ok' : s === 'blocked' || s === 'skipped' ? 'warn' : ''
const outcomeTone = (o: string | null) => (o === 'rejection' ? 'bad' : o === 'interview' ? 'ok' : '')

async function loadSummary() {
  summary.value = await api.historySummary()
}

async function loadRows() {
  loading.value = true
  try {
    const r = await api.historyApplications({
      company: company.value, status: status.value, q: q.value, offset: page.value * size, limit: size,
    })
    rows.value = r.rows
    total.value = r.total
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

async function open(id: string) {
  try {
    detail.value = await api.historyDetail(id)
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function onImport(ev: Event) {
  const file = (ev.target as HTMLInputElement).files?.[0]
  if (!file) return
  error.value = ''
  msg.value = ''
  try {
    const s = await api.historyImport(file)
    summary.value = s
    msg.value = `Imported ${s.totals?.applications ?? 0} applications.`
    page.value = 0
    await loadRows()
  } catch (e) {
    error.value = (e as Error).message
  }
}

let t: ReturnType<typeof setTimeout> | undefined
watch([company, status, q], () => {
  page.value = 0
  clearTimeout(t)
  t = setTimeout(loadRows, 200)
})
watch(page, loadRows)

onMounted(async () => {
  try {
    await loadSummary()
    if (summary.value?.loaded) await loadRows()
  } catch (e) {
    error.value = (e as Error).message
  }
})

const day = (iso: string | null) => (iso ? iso.slice(0, 10) : '')
</script>

<template>
  <section class="stack">
    <p v-if="msg" class="notice ok">{{ msg }}</p>
    <p v-if="error" class="notice bad">{{ error }}</p>

    <div class="panel row">
      <div class="grow">
        <h2>Application history</h2>
        <p class="muted">
          Every application from the export, linked to its job, company, resume version and the emails and
          outcomes that followed.
          <span v-if="summary?.loaded">Exported {{ day(summary.generated_at ?? null) }}.</span>
        </p>
      </div>
      <label class="btn">
        Import export (.json)
        <input type="file" accept=".json,application/json" hidden @change="onImport" />
      </label>
    </div>

    <div v-if="!summary?.loaded" class="panel muted">
      No history imported yet. Use the import button with your applications export.
    </div>

    <template v-else>
      <div class="tiles">
        <div v-for="(n, k) in summary.totals" :key="k" class="panel tile">
          <b>{{ n }}</b><span class="muted">{{ k }}</span>
        </div>
      </div>

      <div class="two">
        <div class="panel">
          <h3>By status</h3>
          <div v-for="[s, n] in statuses" :key="s" class="meter" :title="summary.status_definitions[s]">
            <span>{{ s }}</span>
            <span class="bar"><span class="fill" :style="{ width: (n / maxStatus) * 100 + '%' }"></span></span>
            <span class="num">{{ n }}</span>
          </div>
        </div>
        <div class="panel">
          <h3>By company</h3>
          <div v-for="(n, c) in summary.by_company" :key="c" class="meter">
            <span>{{ c }}</span>
            <span class="bar"><span class="fill" :style="{ width: (n / summary.totals.applications) * 100 + '%' }"></span></span>
            <span class="num">{{ n }}</span>
          </div>
          <p class="muted small" style="margin-top: 10px">
            Events: <span v-for="(n, k) in summary.by_event" :key="k">{{ k.replace('_', ' ') }} {{ n }} &middot; </span>
          </p>
        </div>
      </div>

      <div class="panel">
        <div class="filters">
          <select v-model="company">
            <option value="">All companies</option>
            <option v-for="c in summary.companies" :key="c.company_id" :value="c.company_id">{{ c.name }}</option>
          </select>
          <select v-model="status">
            <option value="">All statuses</option>
            <option v-for="[s] in statuses" :key="s" :value="s">{{ s }}</option>
          </select>
          <input v-model="q" placeholder="Search title, req id, resume, notes" />
        </div>
        <p class="muted small">{{ total }} applications{{ loading ? ' (loading)' : '' }}</p>
        <div class="scroll-x">
          <table>
            <thead>
              <tr><th>Applied</th><th>Company</th><th>Role</th><th>Resume</th><th>Status</th><th>Outcome</th><th>Events</th></tr>
            </thead>
            <tbody>
              <tr v-for="r in rows" :key="r.application_id" class="click" @click="open(r.application_id)">
                <td class="mono">{{ day(r.applied_at) }}</td>
                <td>{{ r.company }}</td>
                <td>{{ r.title }} <span class="muted mono">{{ r.req_id }}</span></td>
                <td class="mono">{{ r.resume_version }}</td>
                <td><span class="pill" :class="tone(r.status)">{{ r.status }}</span></td>
                <td><span v-if="r.outcome" class="pill" :class="outcomeTone(r.outcome)">{{ r.outcome }}</span></td>
                <td>{{ r.event_count }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="row pager">
          <button :disabled="page === 0" @click="page--">Previous</button>
          <span class="muted">Page {{ page + 1 }} of {{ pages }}</span>
          <button :disabled="page + 1 >= pages" @click="page++">Next</button>
        </div>
      </div>
    </template>

    <div v-if="detail" class="overlay" @click.self="detail = null">
      <aside class="panel drawer">
        <div class="row">
          <h3 class="grow">{{ detail.title }}</h3>
          <button @click="detail = null">Close</button>
        </div>
        <p>
          {{ detail.company }} &middot; {{ detail.location }}
          <span class="pill" :class="tone(detail.status)">{{ detail.status }}</span>
        </p>
        <dl>
          <dt>Req id</dt><dd class="mono">{{ detail.req_id }}</dd>
          <dt>Applied</dt><dd>{{ detail.applied_at }}</dd>
          <dt>Submitted by</dt><dd>{{ detail.submitted_by_bot }}</dd>
          <dt>Resume</dt><dd class="mono">{{ detail.resume.resume_id }} ({{ detail.resume.version }})</dd>
          <dt>Confirmation</dt><dd class="small">{{ detail.confirmation_source }}</dd>
          <dt>Notes</dt><dd>{{ detail.notes }}</dd>
          <dt>Posting</dt><dd><a :href="detail.url ?? undefined" target="_blank" rel="noopener">{{ detail.url }}</a></dd>
        </dl>
        <h3>Events</h3>
        <p v-if="!detail.events.length" class="muted">No emails or outcomes recorded.</p>
        <ul class="events">
          <li v-for="e in detail.events" :key="e.event_id">
            <span class="pill" :class="outcomeTone(e.type)">{{ e.type.replace('_', ' ') }}</span>
            <span class="mono muted"> {{ e.date }}</span>
            <div class="small">{{ e.detail }}</div>
          </li>
        </ul>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.grow { flex: 1; min-width: 220px; }
.small { font-size: 12px; }
.tiles { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); }
.tile { display: flex; flex-direction: column; }
.tile b { font-size: 24px; }
.two { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
.meter { display: grid; grid-template-columns: 110px 1fr 36px; gap: 8px; align-items: center; margin: 4px 0; font-size: 13px; }
.bar { height: 8px; background: var(--idle-bg); border-radius: 4px; overflow: hidden; }
.fill { display: block; height: 100%; background: var(--brand); }
.num { text-align: right; }
.filters { display: grid; gap: 10px; grid-template-columns: 200px 200px 1fr; margin-bottom: 8px; }
@media (max-width: 700px) { .filters { grid-template-columns: 1fr; } }
.click { cursor: pointer; }
.click:hover { background: var(--idle-bg); }
.pager { justify-content: center; margin-top: 12px; }
.overlay { position: fixed; inset: 0; background: rgba(0, 0, 0, .35); display: flex; justify-content: flex-end; z-index: 20; }
.drawer { width: min(560px, 100%); height: 100%; overflow-y: auto; border-radius: 0; }
dl { display: grid; grid-template-columns: 110px 1fr; gap: 6px 10px; margin: 10px 0; }
dt { color: var(--muted); }
dd { margin: 0; overflow-wrap: anywhere; }
.events { list-style: none; padding: 0; margin: 0; }
.events li { padding: 8px 0; border-bottom: 1px solid var(--line); }
</style>
