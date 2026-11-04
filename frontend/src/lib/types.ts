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
  target_type: 'automation' | 'recipe' | 'rfi' | 'mergecodes'
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
  orientation?: 'rows' | 'columns'
  language?: string
  key_row?: number
  label_column?: string | null
  isin_columns?: string[]
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
  orientation?: 'rows' | 'columns'
  key_row?: number | null
  label_column?: string | null
  language?: string | null
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
  note?: string
  evidence?: string
}

export interface Preview { sheet: string; as_of: string; rows: number; changes: Change[]; stats: Record<ChangeStatus, number>; language?: string | null; errors?: string[] }

/* ---------------------------------------------------------------- Fabric */
export interface FabricStatus {
  state: 'connected' | 'disconnected' | 'error'
  mode: 'mock' | 'fabric'
  server: string
  database: string
  user: string
  client: string
  saved: boolean
  error?: string | null
}

/* ---------------------------------------------------------------- RFI */
export interface FundShare { isin: string; name: string }
export interface FundEntry { pid: string; name: string; shares: FundShare[] }
export interface FundSuggestion { pid: string; name: string; isin: string | null; share_name: string | null; reason: string }

export interface RfiVersion { version: number; file: string; written: number; as_of: string; by: string; created_at: string }

export interface RfiDocument {
  id: string
  filename: string
  suffix: string
  size: number
  user: string
  uploaded_at: string
  versions?: RfiVersion[]
  kind?: 'xlsx' | 'docx'
  language?: RfiLanguage
  question_count?: number
  dropdowns?: number
  placeholders?: number
  notes?: string[]
  suggestions?: FundSuggestion[]
  shares?: DocumentShare[]
  multi_share?: boolean
  form_sources?: FormSource[]
  qvidian_available?: boolean
  qvidian_count?: number
}

export type RfiLanguage = 'fr' | 'en' | 'es' | 'it'

/** Part citée par le document (ISIN) : fonds Product Info et nombre de cases qui la visent. */
export interface DocumentShare { isin: string; known: boolean; pid: string | null; fund: string | null; share_name: string | null; questions: number }

export type RfiStatus = 'auto' | 'review' | 'existing' | 'no_value' | 'unmatched' | 'skipped'

export interface RfiQuestion {
  id: string
  question: string
  location: string
  state: 'empty' | 'placeholder' | 'answered'
  existing: string
  hint: string
  context: string
  options: string[]
  options_source: string
  layout: string
  entity: { isin?: string; via?: string }
  concept: string | null
  concept_label: string | null
  confidence: number
  answer: string | null
  status: RfiStatus
  source: string
  evidence: string | null
  data_date: string | null
  issues: string[]
  reasons: string[]
  understanding: string[]
  suggestion?: string | null
  alternatives: { concept: string; label: string; score: number; answer: string | null }[]
  precedent?: RfiDecision
  sources?: RfiSource[]
  option?: string | null
  /** Toutes les réponses possibles, toutes sources confondues, regroupées et classées (fréquence × récence × fiabilité). */
  choices?: RfiChoice[]
}

export interface RfiChoiceSource {
  kind: string
  label: string
  url: string
  check: string | null
  blocked: boolean
  date: string | null
  uses: number
  ref: string
}

export interface RfiChoice {
  value: string
  score: number
  share: number
  versions: number
  latest: string | null
  uses: number
  why: string
  sources: RfiChoiceSource[]
}

export interface RfiSource {
  kind: 'fabric' | 'kid' | 'prospectus' | 'document' | 'precedent' | string
  label: string
  value?: string | null
  date?: string | null
  snippet?: string
  url?: string
  check?: 'match' | 'mismatch' | 'unknown' | 'fill' | null
  blocked?: boolean
  detail?: string | null
  uses?: number
  weight?: number
  ref?: string
}

export interface PreviewCell { ref: string; v: string; q: string | null }
export interface PreviewSheet {
  name: string; columns: string[]; widths: number[]; rows: { r: number; cells: PreviewCell[] }[]
  merged: Record<string, [number, number]>; hidden: string[]; questions: number
}
export interface RfiPreview { kind: 'xlsx' | 'docx'; sheets: PreviewSheet[]; items: { id: string; label: string; location: string }[] }

export interface FundDocumentFact { field: string; value: unknown; page: number; snippet: string; citation: string; url: string; kind: string }
export interface FundDocuments {
  isin: string; fund?: string; share?: string; problems: string[]; facts: FundDocumentFact[]
  documents: { kind: string; title: string; url: string; path: string; lang: string; source: string; doc_date: string; fetched_at: string }[]
}

export type RfiDecisionKind = 'precedent_confirme' | 'precedent_liaison' | 'precedent_constant' | 'precedent_habituel'
  | 'precedent_meme_fonds' | 'modele_redaction' | 'incoherence' | 'ontologie' | 'aucun'

export interface RfiPrecedent {
  id: string
  origin: string
  file: string
  url: string
  sheet: string
  answer_cell: string
  question: string
  answer: string
  kind: string
  shape: string
  fund: string
  isin: string
  date: string
  comments: string[]
  blocked: boolean
  block_reason: string
  provenance: string
  similarity: number
  check?: 'match' | 'mismatch' | 'unknown' | null
  fabric?: string | null
  evidence?: string
}

export interface RfiDecision {
  kind: RfiDecisionKind
  label: string
  justification: string
  answer: string | null
  concept: string | null
  precedents: RfiPrecedent[]
  template: string | null
}

export interface RfiAnalysis {
  stats: Record<RfiStatus, number>
  language: RfiLanguage
  as_of: string
  errors: string[]
  questions: RfiQuestion[]
  coverage: { total: number; auto: number; review: number; rate: number }
  notes: string[]
  decisions?: Partial<Record<RfiDecisionKind, number>>
  precedents?: number
  form_sources?: FormSource[]
  qvidian_used?: boolean
}

export interface PrecedentStats {
  total: number
  by_origin: Record<string, number>
  by_kind: Record<string, number>
  by_shape: Record<string, number>
  blocked: number
  sources: number
  sources_list: { source_file: string; origin: string; url: string; imported_at: string; entries: number; identity_problem: string }[]
  embedder: string | null
}

export interface PrecedentInventory {
  total: number
  unique_questions: number
  files: number
  usable: { total: number; by_shape: Record<string, number>; by_origin: Record<string, number> }
  to_review: Record<string, number>
  blocked_sources: { source_file: string; identity_problem: string }[]
  ontology_coverage: { auto: number; review: number; none: number }
  top_concepts: { concept: string; label: string; entries: number }[]
  uncovered: { question: string; occurrences: number; funds: number; files: number }[]
  uncovered_total: number
  repeated_with_variants_total: number
  limits: string[]
}

export interface SourceStatus { source: string; ready: boolean; signed_in?: boolean; root?: string | null; site?: string; hint: string }
export interface SharePointStatus { site: string; root: string; graph: SourceStatus | null; local: SourceStatus; active: 'graph' | 'local' | null }
export interface RemoteItem { id: string; name: string; path: string; is_folder: boolean; url: string; modified: string; size: number }
export interface DueDiligenceList { year: number | null; folders: RemoteItem[]; years: number[]; tried?: number[] }
export interface FinalListing { final_path: string | null; documents: (RemoteItem & { fund?: string })[]; funds: { fund: string; final_path: string }[]; hint: string }
export interface SharePointSyncState {
  running: boolean; phase?: string; folders?: number; found?: number; todo?: number; done?: number; imported?: number; skipped?: number
  failed?: number; stopped?: boolean; started?: string; finished?: string | null
  errors?: { file: string; message: string; hint: string }[]
  corpus: { documents: number; questions: number; failed: number; last: string }
}
export interface SharePointImport { final_path: string | null; imported: number; hint: string; documents: { file: string; imported: number; identity_problem?: string; error?: string }[] }

export interface RfiGenerated extends RfiAnalysis {
  version: number; written: number; file: string; download: string; highlighted?: number; to_ask?: { question: string; location: string }[]
}

export interface RfiFact { id: string; label: string; label_en?: string; scope: string; type: string; source: string; healthy: boolean }

export interface RfiRequest {
  pid?: string | null
  isin?: string | null
  as_of?: string | null
  language?: RfiLanguage | null
  overrides?: Record<string, string | null | { text: string }>
  overwrite?: boolean
  accept?: string[]
  reusable?: string[]
  remember?: boolean
  /** true : recalcul complet (bouton « Analyser ») ; sinon seules les cases modifiées sont recalculées */
  fresh?: boolean
  /** bibliothèque Qvidian comme source (option de l'écran) */
  use_qvidian?: boolean
  /** au téléchargement : cases sans réponse surlignées en jaune (à demander) */
  highlight_missing?: boolean
}

export interface FormSource { file: string; shared: number; overlap: number; date: string }

/* ---------------------------------------------------------------- Merge codes */
export interface MergeProposition {
  code: string
  merge_code: string
  libelle: string
  type: string
  valeur_excel: number | null
  incomplet: boolean
  statut: string
}

export interface MergeCandidate {
  index: number
  texte_id: string
  titre: string
  type: string
  sur: boolean
  valeur_texte: string
  cadre: string
  remarques: string[]
  avant: string
  nombre: string
  apres: string
  propositions: MergeProposition[]
}

export interface MergeReferentiel {
  present: boolean
  meta?: { filename: string; uploaded_at: string } | null
  personnes?: number
  codes_equipe?: number
  annee?: number
  anomalies?: string[]
  nb_anomalies?: number
}

export interface MergeAnalysis {
  id: string
  filename: string
  textes: number
  ids: string[]
  candidats: MergeCandidate[]
  signalements: { texte_id: string; motif: string; extrait: string }[]
  referentiel: MergeReferentiel
}

export interface MergeDecision { choix: 'proposition' | 'ignorer' | 'code'; proposition?: number; code?: string }

export interface MergeResult {
  document: string
  rapport: string
  statuts: Record<string, number>
  inseres: number
  journal: string
  document_url: string
  rapport_url: string
}

export interface Binding {
  id: string; question: string; target: string; label: string; type: string; support: number; compared: number; rate: number
  status: 'candidate' | 'validated' | 'rejected' | 'ambiguous' | 'weak'; runner_up: string; examples: string[]; usable: boolean; strong: boolean
}

export interface FundShopProblem { code: string; title: string; why: string; fix: string; link: string }
export interface FundShopResult {
  id: string; status: 'OK' | 'DÉJÀ PRÉSENT' | 'ÉCHEC'; title: string; why: string; fix: string; code: string; link: string
  file: string; url: string; size: number; at: string; period: string
}
export interface FundShopItem {
  id: string; isin: string; kind: string; fund: string; part: string; month: string; filename: string; active: boolean; overwrite: boolean
  target?: string; period_label?: string; present?: boolean; error?: string; result?: FundShopResult | null
}
export interface FundShopOverview {
  items: FundShopItem[]; destination: string; default_name: string
  types: { key: string; label: string; needs_month: boolean }[]
  memory: { shares: number; funds: number; pages: number; id_column: Record<string, string>; langs: Record<string, string> }
  last_run: { at: string; destination: string; network: string; blocked: FundShopProblem | null } | null
  imported?: number; duplicates?: number; errors?: string[]
}
export interface FundShopAvailable {
  isin: string; fund: string; part: string; page: string; problem: FundShopProblem | null
  documents: { kind: string; label: string; needs_month: boolean; url: string; months: { value: string; label: string; url: string }[] }[]
}
export interface FundShopCheck {
  ok: number; total: number
  results: { line: string; fund: string; part: string; page: string; steps: string[]; documents: Record<string, number>; ok: boolean; problem: string }[]
}
export interface FundShopDiagnostic { ok: boolean; network: string; checks: { label: string; ok: boolean; message: string; fix?: string }[] }

export interface OmniOverview {
  root: string; inbox: string; outlook: boolean; sender: string; jump_excel: boolean
  next: { periode: string; mois: number; annee: number; date_arrete: string; source: string }
  reports: { file: string; periode: string; statut: string; date_arrete: string; alertes: string[]; holdings: number | null; controle_net: string | null }[]
}

export interface CopilotLine {
  id: string; question: string; answer: string; citation: string; confidence: string; previous: string | null
  verdict: 'ok' | 'not_found' | 'rejected'; reason: string; differs?: boolean
}
export interface CopilotAnswers {
  overrides: Record<string, { text: string; source: 'copilot'; citation: string; confidence: string; previous: string | null }>
  rejected: { id: string; question: string; reason: string }[]
  lines?: CopilotLine[]; read?: number; unknown?: string[]
}
export interface CopilotPrompt {
  batches: { prompt: string; labels: string[]; chars: number }[]; labels: Record<string, string>; count: number; fund: string; share: string
  documents: { kind: string; title: string; name: string; download: string; url: string }[]
}

/* ---------------------------------------------------------------- Qvidian */
export interface QvidianStatus {
  mode: 'demo' | 'qvidian' | 'off'
  connected: boolean
  user: string
  auth_url: string
  sso: boolean
  sso_suffix: boolean
  last_sso_error?: string
  credentials: boolean
  write_enabled: boolean
  locked: number
  snapshot: { source?: string; synced_at?: string; count?: string }
  sync: { running: boolean; message: string; done: number; kind?: string; error: { code: string; message: string; hint: string } | null; result: QvidianSyncResult | null }
  half_life_days: number
  extended_fields: boolean
  connected_by?: string
  api_key_configured?: boolean
  connect_error?: string
  credentials_from?: '' | 'env' | 'app'
  remembered?: { remembered: boolean; user: string; protection: '' | 'dpapi' | 'local' }
}

export interface QvidianIssue { category: string; label: string; severity: 'haute' | 'moyenne' | 'basse'; message: string; excerpt: string; fix?: string; others?: number[] }
export interface QvidianItem {
  id: number; title: string; folder_path: string; group: string; enabled: boolean; times_used: number; last_used: string | null
  modified: string | null; revision: number; issues: QvidianIssue[]; text: string
}
export interface QvidianAudit {
  today: string
  contents: number
  with_issues: number
  categories: { key: string; label: string; severity: string; count: number }[]
  groups: { group: string; total: number; with_issues: number; counts: Record<string, number> }[]
  items: QvidianItem[]
}
export interface QvidianContent {
  id: number; revision: number; title: string; text: string; folder_path: string; language: string; enabled: boolean; expired: boolean
  created: string | null; modified: string | null; last_used: string | null; expires: string | null; times_used: number; owners: string
  inline_edit: boolean; checked_out: boolean; checked_out_by: string; alert_text: string; comments: string
  question?: string; learned_terms?: string; folder_id?: number; type?: string; modified_by?: string; revision_label?: string
  insight?: QvidianInsight | null
  versions: { revision: number; title: string; text: string; modified: string | null; seen_at: string }[]
}
export interface QvidianSuggest { question: string; half_life_days: number; choices: (RfiChoice & { contents: string[] })[] }
export interface QvidianAiPrompt { batches: { prompt: string; ids: number[]; chars: number }[]; count: number }
export interface QvidianAiReply { read: number; unknown: string[]; saved: number; findings: Record<string, { kind: string; severity: string; problem: string; fix: string }[]> }
export interface QvidianPlanItem { id: number; title: string; field: string; before: string; after: string; warnings: string[] }
export interface QvidianPlan { id: string; action: string; label: string; params: Record<string, unknown>; items: QvidianPlanItem[]; unchanged: number[]; warnings: number }
export interface QvidianApplyResult { batch: string; written: number; skipped: number; failed: number; results: { id: number; ok: boolean; skipped: boolean; error: string }[] }
export interface QvidianJournalEntry {
  batch: string; at: string; user: string; source: string; action: string; label: string; force: boolean; undo_of: string | null
  items: { id: number; title: string; field: string; before: unknown; after: unknown; ok: boolean }[]
}
export interface QvidianSyncResult {
  mode?: 'full' | 'delta'; contents: number; folders?: number; previews: number; problems: string[]; seconds?: number; workers?: number
  since?: string; changed?: number; removed?: number
}

/* ---------------------------------------------------------------- Qvidian : recherche sémantique */
export type QvidianScope = 'societe' | 'strategie' | 'fonds' | 'part' | 'generique'
export interface QvidianLevel {
  scope: QvidianScope; scope_label: string; confidence: number; funds: string[]; isins: string[]; themes: string[]; theme_labels: string[]; clues: string[]
}
export interface QvidianVariant { id: number; title: string; times_used: number; last_used: string | null; modified: string | null; expired: boolean }
export interface QvidianHit {
  id: number; title: string; question: string; folder_path: string; snippet: string; highlights: [number, number][]; text: string
  score: number | null; relative: number | null; times_used: number; last_used: string | null; modified: string | null; enabled: boolean
  expired: boolean; language: string; type: string; level: QvidianLevel; issues: QvidianIssue[]; why: string[]; variants: QvidianVariant[]
  history?: QvidianHistoryInfo | null
  signals?: { lexical: number; semantic: number | null; rerank: number | null; coverage: number; ranks: Record<string, number>; phrase: boolean; matched: string[] }
}
export interface QvidianFacet { value: string; count: number; label?: string }
export interface QvidianFilters {
  scope?: string[]; theme?: string[]; fund?: string[]; folder?: string; language?: string; min_uses?: number
  include_disabled?: boolean; include_expired?: boolean; only_issues?: boolean
}
export interface QvidianEngineInfo { lexical: boolean; encoder: string | null; reranker: string | null; documents: number; build_seconds: number; funds: string[] }
export interface QvidianSearchResult {
  query: string; language: string | null; pivot: string | null; expansions: string[]; level: QvidianLevel; results: QvidianHit[]; total: number
  timings: Record<string, number>; engine: QvidianEngineInfo; facets: Record<'scope' | 'theme' | 'fund' | 'folder' | 'language', QvidianFacet[]>
  sort: string; index?: { running: boolean; message: string; done: number; total: number; error?: string } | null
}
export interface QvidianHistoryInfo {
  files: number; last: string; questions: string[]; examples: { file: string; date: string; question: string; mode: string; fund: string }[]
}
export interface QvidianHistorySummary {
  built_at: string | null; precedents: number; links: number; contents: number; files: number; questions: number
  by_mode: Record<string, number>; state: { running: boolean; error: string | null }
  top: { id: number; title: string; files: number; last: string; questions: string[] }[]
}
export interface QvidianInsight {
  history?: QvidianHistoryInfo | null
  level: QvidianLevel; issues: QvidianIssue[]; popularity: number
  similar: { id: number; title: string; folder_path: string; score: number; times_used: number; level: QvidianLevel; same_text: boolean }[]
}
export interface QvidianOverview {
  facets: QvidianSearchResult['facets']; engine: QvidianEngineInfo; never_used: number; uses_total: number
  top_used: { id: number; title: string; times_used: number; level: QvidianLevel }[]
}
export interface QvidianModel {
  id: string; kind: 'encoder' | 'reranker'; label: string; size_mb: number; license: string; note: string; installed: boolean; active: boolean
  error?: string | null
  download: { running: boolean; queued?: boolean; done: number; total: number; error: string | null; hint?: string; host?: string; via?: string; file: string
    attempts?: { via: string; host: string; error: string }[] } | null
  links?: { name: string; url: string; size: number; sha256: string }[]
  packs?: string[]
}
export interface QvidianPack { id: string; label: string; note: string; models: string[]; size_mb: number; installed: boolean }
export interface MatchReport {
  pairs: number; positives: number; auc: number; brier: number; ece: number; threshold: number; target: number
  precision_at_threshold: number | null; recall_at_threshold: number; calibration: string; groups: number
  reliability: { from: number; n: number; predicted: number; observed: number }[]
}
export interface MatchStatus {
  state: { running: boolean; message: string; error: string | null; built_at: string | null; seconds?: number; trained?: boolean; reason?: string }
  stats: { questions: number; distinct: number; files: number; dense: boolean; reranker: boolean; precise: boolean; calibrated: boolean
    report: MatchReport | null; precise_report: MatchReport | null } | null
}
export interface MatchResult {
  ready: boolean; calibrated?: boolean; threshold?: number | null; ms?: number
  matches: { question: string; p: number; files: number; last: string; contents: number[]; precise: boolean; why: string[]
    examples: { file: string; date: string; fund: string; answer: string; content_id: number | null }[] }[]
  answers: { id: number; p: number; files: number; asked: string; title: string; text: string }[]
}
export interface QvidianEngineStatus {
  ready: boolean; engine: QvidianEngineInfo | null; neural_runtime: boolean; models: QvidianModel[]; packs?: QvidianPack[]
  building: { running: boolean; message: string; done: number; total: number; error?: string; seconds?: number } | null
}
export interface QvidianOpStat { op: string; calls: number; errors: number; cached: number; retries: number; kb_in: number; p50_ms: number; p95_ms: number; avg_ms: number }
export interface QvidianApiStats {
  mode: string; cache_entries: number; limiter_wait_s: number; delta_supported: boolean | null
  telemetry: { since: string; calls: number; errors: number; cached: number; cache_rate: number; error_rate: number; p50_ms: number; p95_ms: number; kb_in: number
    operations: QvidianOpStat[]; recent: { at: string; op: string; ms: number; ok: boolean; code: string | null; cached: boolean; bytes: number; retries: number }[] } | null
  settings: { concurrency: number; max_calls_per_second: number; cache_seconds: number; keepalive_minutes: number; search_encoder: string; search_reranker: boolean }
  snapshot: Record<string, string>; last_sync: QvidianSyncResult | null
}
export interface QvidianFolder { id: number; parent_id: number; title: string; path: string; contents: number }

export interface QvidianImport { projects: number; total: number; imported: number; documents: { project: string; file?: string; imported?: number; error?: string }[] }
