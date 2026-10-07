export type ParamType = 'string' | 'text' | 'number' | 'integer' | 'date' | 'boolean' | 'select' | 'multiselect' | 'isin'

export interface Option { value: string | number; label: string }

export interface ParamSpec {
  name: string
  label: string
  type: ParamType
  required: boolean
  default: unknown
  help?: string | null
  placeholder?: string | null
  options?: Option[] | null
  options_query?: string | null
  min?: number | null
  max?: number | null
}

export interface Automation {
  id: string
  name: string
  description: string
  icon: string
  category: string
  type: 'python' | 'fabric'
  version: string
  author: string
  tags: string[]
  estimated_minutes_saved: number
  params: ParamSpec[]
  outputs: { type: string; label: string }[]
  steps: string[]
  requires: string[]
  healthy: boolean
  problems: string[]
  query?: string | null
  stats?: { runs: number; success: number; last_at: string | null }
  recent_runs?: Run[]
}

export type RunStatus = 'queued' | 'running' | 'success' | 'error' | 'cancelled'

export interface RunOutput { name: string; kind: string; label: string; size: number }

export interface Run {
  id: string
  target_type: 'automation' | 'recipe'
  target_id: string
  target_name: string
  user: string
  trigger: 'manual' | 'schedule'
  params: Record<string, unknown>
  status: RunStatus
  created_at: string
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  summary: string | null
  error: string | null
  error_hint: string | null
  outputs: RunOutput[]
  minutes_saved: number
  data_mode: string | null
  demo?: boolean
  events?: RunEvent[]
}

export type RunEvent =
  | { type: 'status'; status: RunStatus; ts: string; seq?: number }
  | { type: 'plan'; steps: string[]; ts: string; seq?: number }
  | { type: 'log'; level: 'debug' | 'info' | 'success' | 'warning' | 'error'; message: string; ts: string; seq?: number }
  | { type: 'progress'; value: number; message?: string | null; ts: string; seq?: number }
  | { type: 'step'; name: string; status: 'running' | 'done' | 'error'; index: number | null; duration?: number; ts: string; seq?: number }
  | { type: 'output'; name: string; kind: string; label: string; size: number; ts: string; seq?: number }
  | { type: 'table'; title: string; columns: string[]; rows: unknown[][]; total_rows: number; ts: string; seq?: number }
  | { type: 'summary'; text: string; metrics: Record<string, unknown>; ts: string; seq?: number }
  | { type: 'result'; status: RunStatus; summary?: string | null; error?: string; hint?: string; duration_ms?: number; ts: string; seq?: number }

export interface Schedule {
  id: string
  target_type: 'automation' | 'recipe'
  target_id: string
  label: string
  params: Record<string, unknown>
  frequency: 'daily' | 'weekly' | 'monthly'
  hour: number
  minute: number
  weekday: number | null
  day_of_month: number | null
  enabled: boolean
  created_by: string
  created_at: string
  next_run: string | null
  description: string
}

export interface Alert { level: 'info' | 'warning' | 'error'; code: string; title: string; detail: string; run_id?: string }

export interface Dashboard {
  counters: {
    spells_total: number
    spells_week: number
    success_rate: number | null
    minutes_saved_total: number
    minutes_saved_month: number
    running: number
  }
  running: Run[]
  scheduled: Schedule[]
  activity: { day: string; success: number; error: number }[]
  team: { user: string; runs: number; minutes_saved: number; last_at: string }[]
  recent: Run[]
  top: { id: string; name: string; count: number }[]
  alerts: Alert[]
  data_mode: string
  has_demo_history: boolean
}

export interface Health { status: string; data_mode: 'mock' | 'fabric'; automations: number; broken: number; fabric_configured: boolean }

/* ---------------------------------------------------------------- Atelier */
export interface GridCell { v: string; f: boolean; n: boolean }

export interface ColumnInfo {
  letter: string
  index: number
  header: string
  is_key: boolean
  empty: number
  filled: number
  formulas: number
  highlighted: number
  suggestions: { extraction: string; label: string; score: number }[]
  proposed: string | null
  samples: string[]
}

export interface KeyCandidate { column: string; index: number; key_type: string; score: number; recognized: number; total: number }

export interface SheetAnalysis {
  name: string
  max_row: number
  max_col: number
  header_row: number
  data_rows: number
  key: KeyCandidate | null
  key_candidates: KeyCandidate[]
  key_rows: number
  columns: ColumnInfo[]
  targets: string[]
  target_count: number
  grid: { rows: GridCell[][]; cols: string[]; truncated_rows: boolean; truncated_cols: boolean }
}

export interface WorkbookVersion { name: string; size: number; created_at: string; version?: number; written?: number; as_of?: string; by?: string; recipe_name?: string }

export interface WorkbookAnalysis {
  id: string
  filename: string
  size: number
  uploaded_by: string
  uploaded_at: string
  versions: WorkbookVersion[]
  sheets: SheetAnalysis[]
  suggested_sheet: string | null
}

export interface WorkbookMeta { id: string; filename: string; size: number; uploaded_by: string; uploaded_at: string; version_count: number }

export interface Extraction {
  id: string
  label: string
  group: string
  key: string
  format: string
  synonyms: string[]
  source: string
  caution: string | null
  healthy: boolean
  problems: string[]
}

export interface Mapping { column: string; extraction: string }

export interface Recipe {
  id?: string
  name: string
  workbook_id: string
  sheet: string
  header_row: number
  key_column: string
  key_type: string
  as_of?: string | null
  overwrite: boolean
  highlight_changes: boolean
  mappings: Mapping[]
  created_by?: string
  updated_at?: string
  workbook?: string | null
}

export type ChangeStatus = 'fill' | 'overwrite' | 'conflict' | 'unchanged' | 'not_found' | 'protected'

export interface Change {
  cell: string
  row: number
  column: string
  key: string
  extraction: string
  format: string
  status: ChangeStatus
  before: string
  after: string
}

export interface Preview { sheet: string; as_of: string; rows: number; changes: Change[]; stats: Record<ChangeStatus, number> }
