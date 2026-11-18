import { getUserName } from './storage'
import { texts } from '../content/texts'
import type {
  CopilotAnswers,
  CopilotPrompt,
  FundShopAvailable,
  FundShopCheck,
  FundShopDiagnostic,
  FundShopProblem,
  QvidianAiPrompt, QvidianAiReply, QvidianApplyResult, QvidianAudit, QvidianContent, QvidianImport, QvidianJournalEntry, QvidianPlan,
  QvidianStatus, QvidianSuggest, QvidianApiStats, QvidianEngineStatus, QvidianFilters, QvidianFolder, QvidianOverview, QvidianSearchResult, QvidianHistorySummary,
  Automation, Dashboard, FabricStatus, FundEntry, MergeAnalysis, MergeDecision, MergeReferentiel, MergeResult,
  RfiAnalysis, RfiDocument, RfiFact, RfiGenerated, RfiRequest, PrecedentStats, PrecedentInventory, SharePointStatus,
  DueDiligenceList, FinalListing, SharePointImport, SharePointSyncState, ContactGroup, ContactsStatus, AskPlan, MatchResult, MatchStatus, QvidianMemory, QvidianFreshness, QvidianFamily, QvidianBank, FundSheet, RfiPreview, FundDocuments, Binding, FundShopItem, FundShopOverview, OmniOverview, Extraction, Health, Option, Preview, Recipe, Run, Schedule, WorkbookAnalysis, WorkbookMeta,
} from './types'

export class ApiError extends Error {
  hint: string
  status: number
  constructor(message: string, hint = '', status = 0) {
    super(message)
    this.hint = hint
    this.status = status
  }
}

function headers(extra: Record<string, string> = {}): Record<string, string> {
  const name = getUserName()
  return { ...(name ? { 'X-Merlin-User': encodeURIComponent(name) } : {}), ...extra }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, { ...init, headers: headers(init.headers as Record<string, string>) })
  } catch {
    throw new ApiError(texts.errors.network, texts.errors.networkHint)
  }
  if (!response.ok) {
    let message: string = texts.errors.generic
    let hint = ''
    try {
      const body = await response.json()
      message = body?.detail?.message ?? message
      hint = body?.detail?.hint ?? ''
    } catch {
      if (response.status >= 500) {
        message = texts.errors.network
        hint = texts.errors.networkHint
      }
    }
    throw new ApiError(message, hint, response.status)
  }
  return response.json() as Promise<T>
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  body: JSON.stringify(body),
  headers: { 'Content-Type': 'application/json' },
})

export const api = {
  health: () => request<Health>('/health'),
  automations: () => request<{ automations: Automation[]; broken: { folder: string; problems: string[] }[] }>('/automations'),
  automation: (id: string) => request<Automation>(`/automations/${id}`),
  options: (id: string, param: string) => request<Option[]>(`/automations/${id}/options/${param}`),
  run: (id: string, params: Record<string, unknown>) => request<Run>(`/automations/${id}/run`, json({ params })),
  runs: (query = '') => request<Run[]>(`/runs${query}`),
  getRun: (id: string) => request<Run>(`/runs/${id}`),
  cancel: (id: string) => request<{ ok: boolean }>(`/runs/${id}/cancel`, { method: 'POST' }),
  fileUrl: (runId: string, name: string) => `/api/runs/${runId}/files/${encodeURIComponent(name)}`,
  dashboard: () => request<Dashboard>('/dashboard'),
  clearDemo: () => request<{ ok: boolean }>('/demo-history', { method: 'DELETE' }),
  schedules: () => request<Schedule[]>('/schedules'),
  createSchedule: (body: Partial<Schedule> & { target_type: string; target_id: string; frequency: string }) =>
    request<Schedule>('/schedules', json(body)),
  toggleSchedule: (id: string, enabled: boolean) =>
    request<Schedule>(`/schedules/${id}`, { method: 'PATCH', body: JSON.stringify({ enabled }), headers: { 'Content-Type': 'application/json' } }),
  deleteSchedule: (id: string) => request<{ ok: boolean }>(`/schedules/${id}`, { method: 'DELETE' }),
  suggest: (body: { title: string; description: string; urgency: string }) => request('/suggestions', json(body)),

  omni: () => request<OmniOverview>('/omni'),

  fundshop: {
    overview: () => request<FundShopOverview>('/fundshop'),
    save: (items: Partial<FundShopItem>[]) => request<FundShopOverview>('/fundshop', { method: 'PUT', body: JSON.stringify(items), headers: { 'Content-Type': 'application/json' } }),
    templateUrl: (withList = false) => `/api/fundshop/template.xlsx${withList ? '?with_list=true' : ''}`,
    importExcel: (file: File, replaceAll = false) => {
      const form = new FormData()
      form.append('file', file)
      return request<FundShopOverview>(`/fundshop/import?replace_all=${replaceAll}`, { method: 'POST', body: form })
    },
    learnCsv: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return request<{ learned: number }>('/fundshop/learn-csv', { method: 'POST', body: form })
    },
    link: (isin: string, url: string, kind?: string) => request<{ message: string }>('/fundshop/link', json({ isin, url, kind })),
    tryOne: (isin: string, kind: string, month: string, fund: string) =>
      request<{ found: boolean; url?: string; note?: string; problem?: FundShopProblem }>('/fundshop/try', json({ isin, kind, month, fund })),
    diagnostic: () => request<FundShopDiagnostic>('/fundshop/diagnostic'),
    check: (lines: string[]) => request<FundShopCheck>('/fundshop/check', json({ lines })),
    available: (isin: string, fund: string, part: string) =>
      request<FundShopAvailable>(`/fundshop/available/${isin}?fund=${encodeURIComponent(fund)}&part=${encodeURIComponent(part)}`),
    fileUrl: (name: string) => `/api/fundshop/file/${encodeURIComponent(name)}`,
    bundleUrl: () => '/api/fundshop/bundle.zip',
  },

  fabric: {
    status: () => request<FabricStatus>('/fabric'),
    connect: (body: { server: string; database: string; user: string }) => request<FabricStatus>('/fabric/connect', json(body)),
    disconnect: () => request<FabricStatus>('/fabric/disconnect', { method: 'POST' }),
  },

  contacts: {
    status: () => request<ContactsStatus>('/contacts'),
    scan: (months: number) => request<ContactsStatus>('/contacts/scan', json({ months })),
    stop: () => request<ContactsStatus>('/contacts/stop', { method: 'POST' }),
    questions: (q = '', team = '', dd = '') => request<ContactGroup[]>(`/contacts/questions?q=${encodeURIComponent(q)}&team=${encodeURIComponent(team)}&dd=${encodeURIComponent(dd)}`),
    exportUrl: '/api/contacts/export.xlsx',
    importFiles: (files: File[]) => {
      const form = new FormData()
      files.forEach((f) => form.append('files', f))
      return request<ContactsStatus & { corrections: number; collected: { by: string; mails: number }[] }>('/contacts/import', { method: 'POST', body: form })
    },
    ask: (questions: string[], client = '', fund = '', deadline = '') => request<AskPlan>('/contacts/ask', json({ questions, client, fund, deadline })),
  },
  qvidian: {
    status: () => request<QvidianStatus>('/qvidian/status'),
    connect: (user: string, password: string, apiKey: string, remember = true, authUrl = '') =>
      request<QvidianStatus>('/qvidian/connect', json({ user, password, api_key: apiKey, remember, auth_url: authUrl })),
    forget: () => request<QvidianStatus>('/qvidian/credentials/forget', { method: 'POST' }),
    disconnect: () => request<QvidianStatus>('/qvidian/disconnect', { method: 'POST' }),
    ssoStart: () => request<{ url: string }>('/qvidian/sso/start'),
    sync: (kind: 'auto' | 'full' | 'delta' = 'auto') => request<QvidianStatus['sync']>(`/qvidian/sync?kind=${kind}`, { method: 'POST' }),
    search: (q: string, filters: QvidianFilters = {}, sort = 'pertinence', rerank = true, k = 20) =>
      request<QvidianSearchResult>('/qvidian/search', json({ q, filters, sort, rerank, k })),
    overview: () => request<QvidianOverview>('/qvidian/overview'),
    engine: () => request<QvidianEngineStatus>('/qvidian/engine'),
    downloadModel: (id: string) => request<unknown>(`/qvidian/engine/models/${id}`, { method: 'POST' }),
    rebuild: () => request<QvidianEngineStatus>('/qvidian/engine/rebuild', { method: 'POST' }),
    downloadPack: (pack: string) => request<QvidianEngineStatus>(`/qvidian/engine/packs/${pack}`, { method: 'POST' }),
    itRequest: (pack: string) => request<{ text: string }>(`/qvidian/engine/it-request?pack=${pack}`),
    stopDownloads: () => request<QvidianEngineStatus>('/qvidian/engine/downloads/stop', { method: 'POST' }),
    uploadModels: (files: File[]) => {
      const form = new FormData()
      files.forEach((f) => form.append('files', f))
      return request<{ installed: { model: string; file: string }[]; ignored: string[]; ready: string[]; engine: QvidianEngineStatus }>('/qvidian/engine/models/upload', { method: 'POST', body: form })
    },
    scanModels: (folder = '') => request<{ installed: { model: string; file: string }[]; ignored: string[]; ready: string[]; folder: string; looked_at: number; engine: QvidianEngineStatus }>('/qvidian/engine/models/scan', json({ folder })),
    memory: () => request<QvidianMemory>('/qvidian/memory'),
    freshness: () => request<QvidianFreshness>('/qvidian/freshness'),
    families: () => request<QvidianFamily[]>('/qvidian/families'),
    questionBank: (q = '', only = '') => request<QvidianBank>(`/qvidian/questions?q=${encodeURIComponent(q)}&only=${only}`),
    exportSelection: async (ids: number[]) => {
      const r = await fetch('/api/qvidian/export.xlsx', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids }) })
      if (!r.ok) throw new ApiError('Export impossible.')
      return r.blob()
    },
    match: (q: string, k = 8) => request<MatchResult>('/qvidian/match', json({ q, k })),
    matchStatus: () => request<MatchStatus>('/qvidian/match/status'),
    matchRebuild: () => request<MatchStatus>('/qvidian/match/rebuild', { method: 'POST' }),
    apiStats: () => request<QvidianApiStats>('/qvidian/api-stats'),
    resetStats: () => request<QvidianApiStats>('/qvidian/api-stats/reset', { method: 'POST' }),
    folders: () => request<QvidianFolder[]>('/qvidian/folders'),
    history: () => request<QvidianHistorySummary>('/qvidian/history'),
    historyRebuild: () => request<QvidianHistorySummary>('/qvidian/history/rebuild', { method: 'POST' }),
    audit: (depth = 2) => request<QvidianAudit>(`/qvidian/audit?depth=${depth}`),
    content: (id: number) => request<QvidianContent>(`/qvidian/contents/${id}`),
    suggest: (q: string) => request<QvidianSuggest>(`/qvidian/suggest?q=${encodeURIComponent(q)}`),
    aiPrompt: (ids: number[]) => request<QvidianAiPrompt>('/qvidian/ai/prompt', json({ ids })),
    aiExport: async (ids: number[]) => {
      const r = await fetch('/api/qvidian/ai/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids }) })
      if (!r.ok) throw new ApiError('Export impossible.')
      const name = /filename="([^"]+)"/.exec(r.headers.get('content-disposition') ?? '')?.[1] ?? 'Qvidian_relecture.json'
      return { blob: await r.blob(), name }
    },
    aiImportXlsx: (files: File[]) => {
      const form = new FormData()
      files.forEach((f) => form.append('files', f))
      return request<{ read: number; texts: number; unknown: number[]; sheets: Record<string, number> }>('/qvidian/ai/import-xlsx', { method: 'POST', body: form })
    },
    aiReply: (text: string, ids: number[]) => request<QvidianAiReply>('/qvidian/ai/reply', json({ text, ids })),
    plan: (ids: number[], action: string, params: Record<string, unknown>) => request<QvidianPlan>('/qvidian/bulk/plan', json({ ids, action, params })),
    apply: (planId: string, password: string, force: boolean) => request<QvidianApplyResult>('/qvidian/bulk/apply', json({ plan_id: planId, password, force })),
    journal: () => request<QvidianJournalEntry[]>('/qvidian/journal'),
    undo: (batch: string, password: string) => request<QvidianApplyResult>(`/qvidian/journal/${batch}/undo`, json({ password })),
    importProjects: (limit: number) => request<QvidianImport>('/qvidian/projects/import', json({ limit })),
  },
  rfi: {
    facts: () => request<RfiFact[]>('/rfi/facts'),
    funds: (q: string) => request<FundEntry[]>(`/rfi/funds?q=${encodeURIComponent(q)}`),
    documents: () => request<RfiDocument[]>('/rfi/documents'),
    document: (id: string) => request<RfiDocument>(`/rfi/documents/${id}`),
    upload: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return request<RfiDocument>('/rfi/documents', { method: 'POST', body: form })
    },
    demo: (kind: 'xlsx' | 'docx' | 'grid') => request<RfiDocument>(`/rfi/demo/${kind}`, { method: 'POST' }),
    copilotPack: async (id: string, body: RfiRequest, includeAuto = false): Promise<Blob> => {
      let response: Response
      try {
        response = await fetch(`/api/rfi/documents/${id}/copilot-pack${includeAuto ? '?include_auto=true' : ''}`, { ...json(body), headers: headers({ 'Content-Type': 'application/json' }) })
      } catch {
        throw new ApiError(texts.errors.network, texts.errors.networkHint)
      }
      if (!response.ok) throw new ApiError(texts.errors.generic, '', response.status)
      return response.blob()
    },
    copilotPrompt: (id: string, body: RfiRequest, includeAuto = false) =>
      request<CopilotPrompt>(`/rfi/documents/${id}/copilot-prompt`, json({ ...body, include_auto: includeAuto })),
    copilotReply: (id: string, body: RfiRequest, text: string, labels: Record<string, string>) =>
      request<CopilotAnswers>(`/rfi/documents/${id}/copilot-reply`, json({ ...body, text, labels })),
    copilotAnswers: (id: string, file: File, body: RfiRequest) => {
      const form = new FormData()
      form.append('file', file)
      const q = new URLSearchParams()
      if (body.pid) q.set('pid', body.pid)
      if (body.isin) q.set('isin', body.isin)
      if (body.as_of) q.set('as_of', body.as_of)
      return request<CopilotAnswers>(`/rfi/documents/${id}/copilot-answers?${q}`, { method: 'POST', body: form })
    },
    answers: (id: string, body: RfiRequest) => request<RfiAnalysis>(`/rfi/documents/${id}/answers`, json(body)),
    generate: (id: string, body: RfiRequest) => request<RfiGenerated>(`/rfi/documents/${id}/generate`, json(body)),
    originalUrl: (id: string) => `/api/rfi/documents/${id}/original`,
    preview: (id: string) => request<RfiPreview>(`/rfi/documents/${id}/preview`),
    fundDocuments: (isin: string, refresh = false) => request<FundDocuments>(`/rfi/fund-documents/${isin}${refresh ? '?refresh=true' : ''}`),
    uploadFundDocument: (isin: string, file: File) => {
      const form = new FormData()
      form.append('file', file)
      return request<FundDocuments>(`/rfi/fund-documents/${isin}`, { method: 'POST', body: form })
    },
    bindings: () => request<Binding[]>('/rfi/precedents/bindings'),
    buildBindings: () => request<{ total: number; by_status: Record<string, number> }>('/rfi/precedents/bindings/build', { method: 'POST' }),
    bindingStatus: (id: string, status: string) => request<Binding>('/rfi/precedents/bindings/status', json({ id, status })),
    precedents: () => request<PrecedentStats>('/rfi/precedents'),
    inventory: () => request<PrecedentInventory>('/rfi/precedents/inventory'),
    importWording: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return request<{ imported: number; files: number; blocked: number; note: string }>('/rfi/precedents/wording', { method: 'POST', body: form })
    },
    importPrecedent: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return request<{ file: string; imported: number; identity_problem: string }>('/rfi/precedents/document', { method: 'POST', body: form })
    },
    sharepoint: {
      status: () => request<SharePointStatus>('/rfi/sharepoint/status'),
      dueDiligences: (year?: number | null, q = '') =>
        request<DueDiligenceList>(`/rfi/sharepoint/due-diligences?${year ? `year=${year}&` : ''}q=${encodeURIComponent(q)}`),
      final: (path: string, fund = '') => request<FinalListing>(`/rfi/sharepoint/final?path=${encodeURIComponent(path)}&fund=${encodeURIComponent(fund)}`),
      importFinal: (path: string, fund = '') => request<SharePointImport>('/rfi/sharepoint/import', json({ path, fund })),
      sync: (full = false) => request<SharePointSyncState>('/rfi/sharepoint/sync', json({ full })),
      syncStatus: () => request<SharePointSyncState>('/rfi/sharepoint/sync'),
      syncStop: () => request<SharePointSyncState>('/rfi/sharepoint/sync/stop', { method: 'POST' }),
    },
  },

  merge: {
    referentiel: () => request<MergeReferentiel>('/mergecodes/referentiel'),
    uploadReferentiel: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return request<MergeReferentiel>('/mergecodes/referentiel', { method: 'POST', body: form })
    },
    demo: () => request<MergeAnalysis>('/mergecodes/demo', { method: 'POST' }),
    upload: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return request<MergeAnalysis>('/mergecodes/documents', { method: 'POST', body: form })
    },
    apply: (id: string, decisions: MergeDecision[]) => request<MergeResult>(`/mergecodes/documents/${id}/appliquer`, json({ decisions })),
  },

  atelier: {
    fundSheet: (isin: string, asOf = '') => request<FundSheet>(`/atelier/fund-sheet?isin=${encodeURIComponent(isin)}&as_of=${asOf}`),
    fundSheetXlsx: (isin: string, asOf = '') => `/api/atelier/fund-sheet.xlsx?isin=${encodeURIComponent(isin)}&as_of=${asOf}`,
    extractions: () => request<{ key_types: { id: string; label: string }[]; extractions: Extraction[] }>('/atelier/extractions'),
    workbooks: () => request<WorkbookMeta[]>('/atelier/workbooks'),
    workbook: (id: string, sheet?: string, headerRow?: number, orientation?: 'rows' | 'columns') => {
      const params = new URLSearchParams()
      if (sheet) params.set('sheet', sheet)
      if (sheet && headerRow) params.set('header_row', String(headerRow))
      if (sheet && orientation) params.set('orientation', orientation)
      const query = params.toString()
      return request<WorkbookAnalysis>(`/atelier/workbooks/${id}${query && (headerRow || orientation) ? `?${query}` : ''}`)
    },
    upload: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return request<WorkbookAnalysis>('/atelier/workbooks', { method: 'POST', body: form })
    },
    demo: () => request<WorkbookAnalysis>('/atelier/demo', { method: 'POST' }),
    deleteWorkbook: (id: string) => request(`/atelier/workbooks/${id}`, { method: 'DELETE' }),
    originalUrl: (id: string) => `/api/atelier/workbooks/${id}/original`,
    versionUrl: (id: string, name: string) => `/api/atelier/workbooks/${id}/versions/${encodeURIComponent(name)}`,
    preview: (recipe: Recipe) => request<Preview>('/atelier/preview', json(recipe)),
    run: (recipe: Recipe) => request<Run>('/atelier/run', json(recipe)),
    recipes: () => request<Recipe[]>('/atelier/recipes'),
    saveRecipe: (recipe: Recipe) => request<Recipe>('/atelier/recipes', json(recipe)),
    runRecipe: (id: string) => request<Run>(`/atelier/recipes/${id}/run`, { method: 'POST' }),
    deleteRecipe: (id: string) => request(`/atelier/recipes/${id}`, { method: 'DELETE' }),
  },
}
