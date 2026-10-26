<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { statusTone, pct } from '../format'
import type { Application, Draft } from '../types'

const apps = ref<Application[]>([])
const selected = ref('')
const draft = ref<Draft | null>(null)
const resumeText = ref('')
const subject = ref('')
const body = ref('')
const who = ref('me')
const error = ref('')
const msg = ref('')

const current = computed(() => apps.value.find((a) => a.id === selected.value))

async function loadApps() {
  try {
    apps.value = (await api.applications()).applications
    if (!selected.value && apps.value.length) selected.value = apps.value[0].id
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function loadDraft() {
  draft.value = null
  if (!selected.value) return
  try {
    const d = await api.draft(selected.value)
    draft.value = d
    resumeText.value = d.resume_text
    subject.value = d.email_subject
    body.value = d.email_body
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function act(fn: () => Promise<unknown>, ok: string) {
  error.value = ''
  msg.value = ''
  try {
    await fn()
    msg.value = ok
  } catch (e) {
    error.value = (e as Error).message
  }
  await loadApps()
  await loadDraft()
}

const save = () =>
  act(() => api.saveDraft(selected.value, {
    resume_text: resumeText.value, email_subject: subject.value, email_body: body.value,
  }), 'Edits saved and the gates re-ran.')
const approve = () => act(() => api.approve(selected.value, who.value || 'me'), 'Approved by you. Still not submitted anywhere.')
const reject = () => act(() => api.reject(selected.value), 'Rejected.')
const applied = () => act(() => api.markApplied(selected.value), 'Marked applied.')

watch(selected, loadDraft)
onMounted(async () => {
  await loadApps()
  await loadDraft()
})
</script>

<template>
  <section class="stack">
    <p v-if="msg" class="notice ok">{{ msg }}</p>
    <p v-if="error" class="notice bad">{{ error }}</p>

    <div v-if="!apps.length" class="panel muted">Nothing queued yet. Run the pipeline from the Agents or Jobs tab.</div>

    <template v-else>
      <div class="panel row">
        <label for="app" style="margin: 0">Application</label>
        <select id="app" v-model="selected" style="max-width: 520px">
          <option v-for="a in apps" :key="a.id" :value="a.id">{{ a.company }} - {{ a.title }} ({{ a.status }})</option>
        </select>
        <span v-if="current" class="pill" :class="statusTone(current.status)">{{ current.status }}</span>
      </div>

      <template v-if="draft">
        <p v-if="draft.eval_blocked" class="notice">
          Gates failed ({{ (draft.eval.failures ?? []).join(', ') }}). It will not go to approval until this is fixed.
        </p>

        <div class="panel row">
          <span v-if="draft.match_score !== null">Match score <b>{{ draft.match_score?.toFixed(2) }}</b></span>
          <span v-if="draft.tailor_mode" class="pill">{{ draft.tailor_mode }}</span>
          <span v-if="draft.missing_skills.length" class="muted">Missing: {{ draft.missing_skills.join(', ') }}</span>
        </div>

        <div v-if="draft.eval.scores" class="panel">
          <h3>Quality gates</h3>
          <div class="gates">
            <div v-for="(g, name) in draft.eval.scores" :key="name" class="gate">
              <span class="pill" :class="g.passed ? 'ok' : 'bad'">{{ g.passed ? 'pass' : 'fail' }}</span>
              <b>{{ name }}</b> <span class="muted">{{ pct(g.score) }}</span>
              <div v-if="g.detail" class="muted small">{{ g.detail }}</div>
            </div>
          </div>
        </div>

        <div class="panel stack">
          <div><label>Tailored resume</label><textarea v-model="resumeText" rows="14"></textarea></div>
          <div><label>Email subject</label><input v-model="subject" /></div>
          <div><label>Email draft</label><textarea v-model="body" rows="7"></textarea></div>
          <div v-if="draft.contacts.length">
            <label>Contacts (none verified, nothing is emailed)</label>
            <ul class="contacts">
              <li v-for="c in draft.contacts" :key="c.name + c.email">
                {{ c.name }} <span class="mono">{{ c.email }}</span>
                <span class="muted"> {{ c.source }} - confidence {{ c.confidence }}</span>
              </li>
            </ul>
          </div>
        </div>

        <div class="panel row">
          <div style="max-width: 200px"><label>Your name on the approval</label><input v-model="who" /></div>
          <button @click="save">Save edits</button>
          <button class="primary" :disabled="draft.eval_blocked" @click="approve">Approve</button>
          <button class="danger" @click="reject">Reject</button>
          <a class="btn" :href="api.docxUrl(selected)">Download docx</a>
          <button @click="applied">I submitted this myself, mark applied</button>
        </div>
      </template>
    </template>
  </section>
</template>

<style scoped>
.gates { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); margin-top: 10px; }
.gate { border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; }
.small { font-size: 12px; }
.contacts { margin: 4px 0 0; padding-left: 18px; }
</style>
