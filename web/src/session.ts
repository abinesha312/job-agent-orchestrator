import { reactive, watch } from 'vue'

const KEY = 'applypilot.resume_id'
let saved = ''
try {
  saved = localStorage.getItem(KEY) ?? ''
} catch {
  /* storage blocked */
}

export const session = reactive({ resumeId: saved })

watch(
  () => session.resumeId,
  (v) => {
    try {
      localStorage.setItem(KEY, v)
    } catch {
      /* storage blocked */
    }
  },
)
