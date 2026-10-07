import { getUserName } from './storage'
import { texts } from '../content/texts'
import type {
  Automation, Dashboard, Extraction, Health, Option, Preview, Recipe, Run, Schedule, WorkbookAnalysis, WorkbookMeta,
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
