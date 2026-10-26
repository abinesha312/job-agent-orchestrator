import { reactive, watch } from 'vue'

export type Theme = 'light' | 'dark' | 'system'

const KEY = 'applypilot.prefs'

function read(): { theme: Theme; name: string } {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? '{}')
    const theme: Theme = ['light', 'dark', 'system'].includes(raw.theme) ? raw.theme : 'system'
    return { theme, name: typeof raw.name === 'string' ? raw.name : '' }
  } catch {
    return { theme: 'system', name: '' }
  }
}

export const prefs = reactive(read())

export function applyTheme(theme: Theme) {
  const root = document.documentElement
  if (theme === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', theme)
}

applyTheme(prefs.theme)

watch(
  prefs,
  (v) => {
    applyTheme(v.theme)
    try {
      localStorage.setItem(KEY, JSON.stringify({ theme: v.theme, name: v.name }))
    } catch {
      /* storage blocked: the choice lasts for this tab only */
    }
  },
  { deep: true },
)
