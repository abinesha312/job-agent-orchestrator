<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { prefs, type Theme } from '../prefs'

const options: { id: Theme; label: string; hint: string }[] = [
  { id: 'light', label: 'Light', hint: 'Bright background, dark text' },
  { id: 'dark', label: 'Dark', hint: 'Dim background, easy on the eyes' },
  { id: 'system', label: 'System', hint: 'Follow the device setting' },
]

const info = ref('')
onMounted(async () => {
  try {
    const h = await api.health()
    info.value = `API ${h.version} - ${h.storage} storage - ${h.embedder} embeddings`
  } catch {
    info.value = 'API not reachable'
  }
})
</script>

<template>
  <section class="stack">
    <div class="panel stack">
      <h2>Profile</h2>
      <div style="max-width: 360px">
        <label for="name">Display name</label>
        <input id="name" v-model="prefs.name" placeholder="Your name" />
      </div>
    </div>

    <div class="panel stack">
      <h3>Theme</h3>
      <div class="themes" role="radiogroup" aria-label="Theme">
        <label v-for="o in options" :key="o.id" class="opt" :class="{ on: prefs.theme === o.id }">
          <input v-model="prefs.theme" type="radio" name="theme" :value="o.id" />
          <span class="swatch" :data-t="o.id" aria-hidden="true">
            <i></i><i></i><i></i>
          </span>
          <b>{{ o.label }}</b>
          <span class="muted small">{{ o.hint }}</span>
        </label>
      </div>
      <p class="muted small">Saved in this browser.</p>
    </div>

    <div class="panel">
      <h3>About</h3>
      <p class="muted">{{ info }}</p>
    </div>
  </section>
</template>

<style scoped>
.small { font-size: 12px; }
.themes { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); }
.opt { display: flex; flex-direction: column; gap: 6px; border: 1px solid var(--line); border-radius: 10px;
  padding: 12px; cursor: pointer; margin: 0; color: var(--ink); font-size: 14px; }
.opt.on { border-color: var(--brand); box-shadow: 0 0 0 1px var(--brand); }
.opt input { position: absolute; opacity: 0; pointer-events: none; }
.opt:focus-within { outline: 2px solid var(--brand); outline-offset: 2px; }
.swatch { display: flex; gap: 4px; height: 44px; border-radius: 8px; padding: 6px; border: 1px solid var(--line); }
.swatch i { flex: 1; border-radius: 4px; }
.swatch[data-t='light'] { background: #f6f7f9; }
.swatch[data-t='light'] i:nth-child(1) { background: #fff; }
.swatch[data-t='light'] i:nth-child(2) { background: #3b5bdb; }
.swatch[data-t='light'] i:nth-child(3) { background: #e3e6ec; }
.swatch[data-t='dark'] { background: #0f1218; }
.swatch[data-t='dark'] i:nth-child(1) { background: #171b23; }
.swatch[data-t='dark'] i:nth-child(2) { background: #748ffc; }
.swatch[data-t='dark'] i:nth-child(3) { background: #262c38; }
.swatch[data-t='system'] { background: linear-gradient(90deg, #f6f7f9 50%, #0f1218 50%); }
.swatch[data-t='system'] i:nth-child(1) { background: #fff; }
.swatch[data-t='system'] i:nth-child(2) { background: #3b5bdb; }
.swatch[data-t='system'] i:nth-child(3) { background: #262c38; }
</style>
