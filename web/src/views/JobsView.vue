<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { session } from '../session'
import { statusTone } from '../format'
import type { CompanyInfo, CompanySearchResult, Job } from '../types'

const jobs = ref<Job[]>([])
const error = ref('')
const msg = ref('')
const busy = ref('')

const companies = ref<CompanyInfo[]>([])
const companyNote = ref('')
const picked = ref<string[]>([])
const cq = reactive({ query: 'software engineer', limit: 15 })
const found = ref<CompanySearchResult | null>(null)

async function loadCompanies() {
  try {
    const r = await api.companies()
    companies.value = r.companies
    companyNote.value = r.note
  } catch (e) {
    error.value = (e as Error).message
  }
}

const searchCompanies = () =>
  guard('companies', async () => {
    found.value = await api.companySearch({ companies: picked.value, query: cq.query, limit: cq.limit })
    loadCompanies()
    const bad = found.value.errors.length ? ` Problems: ${found.value.errors.join('; ')}` : ''
    return `Saved ${found.value.saved} (${found.value.created} new).${bad}`
  })

const board = reactive({ greenhouse: '', lever: '', ashby: '', roles: '' })
const paste = reactive({ company: '', title: '', url: '', jd_text: '' })
const fromUrl = reactive({ url: '', company: '', title: '' })

const split = (s: string) => s.split(',').map((x) => x.trim()).filter(Boolean)

async function load() {
  try {
    jobs.value = (await api.jobs()).jobs
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function guard(name: string, fn: () => Promise<string>) {
  busy.value = name
  error.value = ''
  msg.value = ''
  try {
    msg.value = await fn()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    busy.value = ''
    load()
  }
}

const discover = () =>
  guard('discover', async () => {
    const r = await api.discover({
      greenhouse: split(board.greenhouse), lever: split(board.lever),
      ashby: split(board.ashby), roles: split(board.roles),
    })
    return `Saved ${r.saved} (${r.created} new).${r.errors.length ? ' Problems: ' + r.errors.join('; ') : ''}`
  })

const savePasted = () =>
  guard('paste', async () => {
    const r = await api.importJob({ ...paste })
    Object.assign(paste, { company: '', title: '', url: '', jd_text: '' })
    return `Saved job ${r.job_id.slice(0, 8)}`
  })

const saveUrl = () =>
  guard('url', async () => {
    const r = await api.importUrl({ url: fromUrl.url, company: fromUrl.company, title: fromUrl.title })
    return `Imported job ${r.job_id.slice(0, 8)}`
  })

const runOne = (id: string) =>
  guard('run:' + id, async () => {
    if (!session.resumeId) throw new Error('Parse a resume first (Resume tab).')
    const r = (await api.run(session.resumeId, [id])).results[0]
    return `${r.status}: ${r.steps.join(' > ')} ${r.notes.join('; ')}`
  })

const runAll = () =>
  guard('all', async () => {
    if (!session.resumeId) throw new Error('Parse a resume first (Resume tab).')
    const r = (await api.run(session.resumeId)).results
    return `Ran ${r.length} jobs. See the Agents tab for the task trail.`
  })

onMounted(() => {
  load()
  loadCompanies()
})
</script>

<template>
  <section class="stack">
    <p v-if="msg" class="notice ok">{{ msg }}</p>
    <p v-if="error" class="notice bad">{{ error }}</p>

    <div class="panel stack">
      <h2>Company careers</h2>
      <p class="muted">
        Reads each company's public job search. No sign-in and no Google OAuth: these sites do not let a third
        party log in for you, so open the posting and apply there yourself.
      </p>
      <div class="cgrid">
        <label v-for="c in companies" :key="c.id" class="ccard" :class="{ on: picked.includes(c.id) }">
          <input v-model="picked" type="checkbox" :value="c.id" />
          <b>{{ c.name }}</b>
          <span class="muted small">{{ c.ats }} &middot; {{ c.saved_jobs }} saved</span>
          <span class="muted small">Sign-in there: {{ c.sign_in }}</span>
          <a :href="c.careers_url" target="_blank" rel="noopener" class="small" @click.stop>Careers site</a>
        </label>
      </div>
      <div class="row">
        <input v-model="cq.query" placeholder="Keywords" style="max-width: 320px" />
        <input v-model.number="cq.limit" type="number" min="1" max="50" style="width: 90px" title="Jobs per company" />
        <button class="primary" :disabled="!!busy || !picked.length" @click="searchCompanies">
          {{ busy === 'companies' ? 'Searching...' : 'Search selected' }}
        </button>
        <button @click="picked = companies.map((c) => c.id)">Select all</button>
      </div>
      <ul v-if="found?.jobs.length" class="found">
        <li v-for="j in found.jobs" :key="j.job_id">
          <b>{{ j.company }}</b>
          <a :href="j.url" target="_blank" rel="noopener">{{ j.title }}</a>
          <span class="muted small">{{ j.location }}</span>
          <span v-if="j.created" class="pill ok">new</span>
        </li>
      </ul>
    </div>

    <div class="panel stack">
      <h2>Find jobs</h2>
      <p class="muted">Public Greenhouse, Lever and Ashby boards. One bad board will not wipe the others.</p>
      <div class="cols">
        <div><label>Greenhouse tokens</label><input v-model="board.greenhouse" placeholder="example, another" /></div>
        <div><label>Lever slugs</label><input v-model="board.lever" /></div>
        <div><label>Ashby boards</label><input v-model="board.ashby" /></div>
        <div><label>Only titles containing</label><input v-model="board.roles" placeholder="backend, python" /></div>
      </div>
      <div><button class="primary" :disabled="!!busy" @click="discover">Run discovery</button></div>
    </div>

    <div class="cols2">
      <form class="panel stack" @submit.prevent="savePasted">
        <h3>Paste a job</h3>
        <input v-model="paste.company" placeholder="Company" required />
        <input v-model="paste.title" placeholder="Title" required />
        <input v-model="paste.url" placeholder="URL" required />
        <textarea v-model="paste.jd_text" rows="6" placeholder="Job text" required></textarea>
        <div><button class="primary" :disabled="!!busy">Save job</button></div>
      </form>
      <form class="panel stack" @submit.prevent="saveUrl">
        <h3>Import from a URL</h3>
        <input v-model="fromUrl.url" placeholder="https://..." required />
        <input v-model="fromUrl.company" placeholder="Company (optional)" />
        <input v-model="fromUrl.title" placeholder="Title (optional)" />
        <div><button class="primary" :disabled="!!busy">Import</button></div>
      </form>
    </div>

    <div class="panel">
      <div class="row">
        <h2 style="flex: 1">Jobs ({{ jobs.length }})</h2>
        <button class="primary" :disabled="!!busy || !jobs.length" @click="runAll">Run matching and drafts on all</button>
      </div>
      <p v-if="!jobs.length" class="muted">No jobs yet.</p>
      <div v-else class="scroll-x">
        <table>
          <thead><tr><th>Company</th><th>Title</th><th>Source</th><th>Status</th><th></th></tr></thead>
          <tbody>
            <tr v-for="j in jobs" :key="j.job_id">
              <td>{{ j.company }}</td>
              <td><a :href="j.url" target="_blank" rel="noopener">{{ j.title }}</a></td>
              <td class="muted">{{ j.source }}</td>
              <td><span class="pill" :class="statusTone(j.status)">{{ j.status ?? 'new' }}</span></td>
              <td><button :disabled="!!busy" @click="runOne(j.job_id)">Run</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>

<style scoped>
.small { font-size: 12px; }
.cgrid { display: grid; gap: 10px; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); }
.ccard { display: flex; flex-direction: column; gap: 2px; border: 1px solid var(--line); border-radius: 8px; padding: 10px; cursor: pointer; margin: 0; color: var(--ink); font-size: 14px; }
.ccard.on { border-color: var(--brand); box-shadow: 0 0 0 1px var(--brand); }
.ccard input { width: auto; align-self: flex-start; }
.found { list-style: none; padding: 0; margin: 0; }
.found li { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; padding: 4px 0; border-bottom: 1px solid var(--line); }
.cols { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }
.cols2 { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
</style>
