import type {
  AgentsOverview, Application, Chunk, Draft, EvalCatalog, EvalRun, HistoryDetail, HistoryRow,
  HistorySummary, Job, PipelineRow, Task,
} from './types'

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

async function call<T>(method: string, path: string, body?: unknown, form?: FormData): Promise<T> {
  const init: RequestInit = { method }
  if (form) init.body = form
  else if (body !== undefined) {
    init.body = JSON.stringify(body)
    init.headers = { 'content-type': 'application/json' }
  }
  let res: Response
  try {
    res = await fetch(`/api${path}`, init)
  } catch {
    throw new ApiError(0, 'API is not reachable. Is the backend running?')
  }
  if (!res.ok) {
    let msg = res.statusText
    try {
      const j = await res.json()
      msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail ?? j)
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, `${res.status}: ${msg}`)
  }
  return (await res.json()) as T
}

export const api = {
  health: () => call<{ status: string; storage: string; embedder: string; version: string }>('GET', '/health'),
  agents: () => call<AgentsOverview>('GET', '/agents'),
  timeline: (jobId?: string) =>
    call<{ count: number; events: Task[] }>('GET', `/agents/timeline${jobId ? `?job_id=${jobId}` : ''}`),
  uploadResume: (file: File) => {
    const f = new FormData()
    f.append('file', file)
    return call<{ resume_id: string; version: number; chunk_count: number; sections: string[] }>(
      'POST', '/resumes', undefined, f)
  },
  chunks: (id: string) => call<{ count: number; version: number; chunks: Chunk[] }>('GET', `/resumes/${id}/chunks`),
  discover: (body: { greenhouse: string[]; lever: string[]; ashby: string[]; roles: string[] }) =>
    call<{ saved: number; created: number; errors: string[] }>('POST', '/discovery', body),
  importJob: (body: { company: string; title: string; url: string; jd_text: string }) =>
    call<{ job_id: string }>('POST', '/jobs/import', body),
  importUrl: (body: { url: string; company?: string; title?: string }) =>
    call<{ job_id: string }>('POST', '/jobs/import-url', body),
  jobs: () => call<{ count: number; jobs: Job[] }>('GET', '/jobs'),
  run: (resume_id: string, job_ids?: string[]) =>
    call<{ results: PipelineRow[] }>('POST', '/pipeline/run', { resume_id, job_ids }),
  applications: () => call<{ count: number; applications: Application[] }>('GET', '/applications'),
  draft: (id: string) => call<Draft>('GET', `/applications/${id}/draft`),
  saveDraft: (id: string, body: { resume_text: string; email_subject: string; email_body: string }) =>
    call<Draft>('PATCH', `/applications/${id}/draft`, body),
  approve: (id: string, approved_by: string) =>
    call<Application>('POST', `/applications/${id}/approve`, { approved_by }),
  reject: (id: string) => call<Application>('POST', `/applications/${id}/reject`),
  markApplied: (id: string) => call<Application>('POST', `/applications/${id}/applied`),
  docxUrl: (id: string) => `/api/applications/${id}/docx`,
  evalCatalog: () => call<EvalCatalog>('GET', '/evals/catalog'),
  evalRun: (suite: string, sample = 5) => call<EvalRun>('POST', '/evals/run', { suite, sample }),
  evalRuns: () => call<{ runs: Omit<EvalRun, 'cases'>[] }>('GET', '/evals/runs'),
  historySummary: () => call<HistorySummary>('GET', '/history/summary'),
  historyApplications: (f: { company?: string; status?: string; q?: string; offset?: number; limit?: number }) => {
    const p = new URLSearchParams()
    for (const [k, v] of Object.entries(f)) if (v !== undefined && v !== '') p.set(k, String(v))
    return call<{ total: number; rows: HistoryRow[] }>('GET', `/history/applications?${p}`)
  },
  historyDetail: (id: string) => call<HistoryDetail>('GET', `/history/applications/${encodeURIComponent(id)}`),
  historyImport: (file: File) => {
    const f = new FormData()
    f.append('file', file)
    return call<HistorySummary>('POST', '/history/import', undefined, f)
  },
  evalRunGet: (id: string) => call<EvalRun>('GET', `/evals/runs/${id}`),
}
