import { getUserName } from './storage'
import { texts } from '../content/texts'
import type {
  Automation, Dashboard, FabricStatus, FundEntry, MergeAnalysis, MergeDecision, MergeReferentiel, MergeResult,
  RfiAnalysis, RfiDocument, RfiFact, RfiGenerated, RfiRequest, PrecedentStats, PrecedentInventory, SharePointStatus,
  DueDiligenceList, FinalListing, SharePointImport, Extraction, Health, Option, Preview, Recipe, Run, Schedule, WorkbookAnalysis, WorkbookMeta,
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

  fabric: {
    status: () => request<FabricStatus>('/fabric'),
    connect: (body: { server: string; database: string; user: string }) => request<FabricStatus>('/fabric/connect', json(body)),
    disconnect: () => request<FabricStatus>('/fabric/disconnect', { method: 'POST' }),
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
    demo: (kind: 'xlsx' | 'docx') => request<RfiDocument>(`/rfi/demo/${kind}`, { method: 'POST' }),
    answers: (id: string, body: RfiRequest) => request<RfiAnalysis>(`/rfi/documents/${id}/answers`, json(body)),
    generate: (id: string, body: RfiRequest) => request<RfiGenerated>(`/rfi/documents/${id}/generate`, json(body)),
    originalUrl: (id: string) => `/api/rfi/documents/${id}/original`,
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
      final: (path: string) => request<FinalListing>(`/rfi/sharepoint/final?path=${encodeURIComponent(path)}`),
      importFinal: (path: string) => request<SharePointImport>('/rfi/sharepoint/import', json({ path })),
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
    extractions: () => request<{ key_types: { id: string; label: string }[]; extractions: Extraction[] }>('/atelier/extractions'),
    workbooks: () => request<WorkbookMeta[]>('/atelier/workbooks'),
    workbook: (id: string, sheet?: string, headerRow?: number) =>
      request<WorkbookAnalysis>(`/atelier/workbooks/${id}${sheet && headerRow ? `?sheet=${encodeURIComponent(sheet)}&header_row=${headerRow}` : ''}`),
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
