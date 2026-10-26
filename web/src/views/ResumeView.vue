<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { session } from '../session'
import type { Chunk } from '../types'

const chunks = ref<Chunk[]>([])
const msg = ref('')
const error = ref('')
const busy = ref(false)
const file = ref<File | null>(null)

async function load() {
  chunks.value = []
  if (!session.resumeId) return
  try {
    chunks.value = (await api.chunks(session.resumeId)).chunks
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
  }
}

function onFile(ev: Event) {
  file.value = (ev.target as HTMLInputElement).files?.[0] ?? null
}

async function upload() {
  if (!file.value) return
  busy.value = true
  msg.value = ''
  error.value = ''
  try {
    const r = await api.uploadResume(file.value)
    session.resumeId = r.resume_id
    msg.value = `Stored v${r.version}: ${r.chunk_count} chunks (${r.sections.join(', ')})`
    await load()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="stack">
    <div class="panel stack">
      <h2>Resume</h2>
      <div class="row">
        <input type="file" accept=".pdf,.docx" @change="onFile" style="max-width: 360px" />
        <button class="primary" :disabled="!file || busy" @click="upload">{{ busy ? 'Parsing...' : 'Parse resume' }}</button>
      </div>
      <div>
        <label for="rid">Resume id</label>
        <input id="rid" v-model="session.resumeId" placeholder="set automatically after upload" @change="load" />
      </div>
      <p v-if="msg" class="notice ok">{{ msg }}</p>
      <p v-if="error" class="notice bad">{{ error }}</p>
    </div>

    <div v-if="chunks.length" class="grid">
      <details v-for="c in chunks" :key="c.id" class="panel">
        <summary><b>#{{ c.order }}</b> {{ c.section }}</summary>
        <pre>{{ c.text }}</pre>
      </details>
    </div>
  </section>
</template>

<style scoped>
pre { white-space: pre-wrap; margin: 10px 0 0; font: inherit; }
summary { cursor: pointer; }
</style>
