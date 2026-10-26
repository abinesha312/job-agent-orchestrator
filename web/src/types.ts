export interface Task {
  id: string
  agent: string
  ok: boolean
  message: string
  job_id: string | null
  resume_id: string | null
  detail: Record<string, unknown>
  created_at: string
}

export interface AgentCard {
  id: string
  name: string
  role: string
  tools: string[]
  order: number
  state: 'idle' | 'done' | 'error'
  tasks_total: number
  tasks_failed: number
  last_run_at: string | null
  last_message: string
  recent_tasks: Task[]
  subagents?: string[]
}

export interface AgentsOverview {
  main: AgentCard
  subagents: AgentCard[]
  total_tasks: number
}

export interface Job {
  job_id: string
  company: string
  title: string
  source: string
  url: string
  posted_at: string | null
  status: string | null
  application_id: string | null
}

export interface Application {
  id: string
  job_id: string
  company: string
  title: string
  source: string
  url: string
  status: string
  approved_by_user: boolean
  applied_at: string | null
  match_score: number | null
  missing_skills: string[]
  eval_blocked: boolean
  eval_failures: string[]
  tailor_mode: string | null
}

export interface Contact {
  name: string
  email: string | null
  source: string
  verified: boolean
  confidence: number
}

export interface GateScore {
  score: number
  passed: boolean
  detail: string
}

export interface Draft {
  id: string
  status: string
  resume_text: string
  email_subject: string
  email_body: string
  eval: { passed?: boolean; failures?: string[]; scores?: Record<string, GateScore> }
  eval_blocked: boolean
  tailor_mode: string | null
  match_score: number | null
  missing_skills: string[]
  contacts: Contact[]
}

export interface Chunk {
  id: string
  section: string
  order: number
  text: string
}

export interface PipelineRow {
  job_id: string
  status: string
  steps: string[]
  needs_human_review: boolean
  notes: string[]
}

export interface EvalSuite {
  id: string
  name: string
  engine: string
  metrics: string[]
  about: string
}

export interface EvalEngine {
  id: string
  name: string
  available: boolean
  reason: string
}

export interface EvalCatalog {
  suites: EvalSuite[]
  engines: EvalEngine[]
  thresholds: Record<string, number>
  gates: { name: string; checks: string; threshold: number | null; hard_fail: boolean }[]
}

export interface EvalCase {
  id: string
  scores: Record<string, number>
  passed: boolean
  notes: string
  checks: Record<string, boolean>
}

export interface EvalRun {
  id: string
  suite: string
  name: string
  engine: string
  started_at: string
  duration_ms: number
  status: 'passed' | 'failed' | 'skipped'
  total: number
  passed: number
  failed: number
  summary: Record<string, number | null>
  cases: EvalCase[]
  notes: string
}

export interface HistoryRow {
  application_id: string
  status: string | null
  applied_at: string | null
  submitted_by_bot: string | null
  notes: string | null
  company_id: string | null
  company: string | null
  job_id: string | null
  req_id: string | null
  title: string | null
  location: string | null
  url: string | null
  resume_id: string | null
  resume_version: string | null
  event_count: number
  outcome: string | null
}

export interface HistoryEvent {
  event_id: string
  application_id: string
  type: string
  date: string
  detail: string
}

export interface HistoryDetail extends HistoryRow {
  confirmation_source: string | null
  resume: { resume_id?: string; version?: string; file_path?: string }
  events: HistoryEvent[]
}

export interface HistorySummary {
  loaded: boolean
  generated_at?: string
  timezone_note?: string
  status_definitions: Record<string, string>
  totals: Record<string, number>
  by_status: Record<string, number>
  by_company: Record<string, number>
  by_event: Record<string, number>
  companies: { company_id: string; name: string }[]
}

export interface CompanyInfo {
  id: string
  name: string
  careers_url: string
  ats: string
  sign_in: string
  how: string
  saved_jobs: number
}

export interface CompanySearchResult {
  saved: number
  created: number
  errors: string[]
  jobs: { job_id: string; company: string; title: string; url: string; location: string; created: boolean }[]
}
