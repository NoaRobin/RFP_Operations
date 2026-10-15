import { useCallback, useEffect, useReducer } from 'react'
import { api } from '../../lib/api'
import { useEventSource } from '../../lib/hooks'
import type { Run, RunEvent, RunOutput, RunStatus } from '../../lib/types'

export interface StepState { name: string; status: 'pending' | 'running' | 'done' | 'error'; duration?: number }
export interface LogLine { id: number; level: string; message: string; ts: string }
export interface TableData { title: string; columns: string[]; rows: unknown[][]; total_rows: number }

export interface RunState {
  run: Run | null
  status: RunStatus
  steps: StepState[]
  logs: LogLine[]
  progress: number | null
  progressMessage: string | null
  outputs: RunOutput[]
  tables: TableData[]
  summary: string | null
  error: string | null
  hint: string | null
  durationMs: number | null
  lastSeq: number
}

const initial: RunState = {
  run: null, status: 'queued', steps: [], logs: [], progress: null, progressMessage: null, outputs: [], tables: [],
  summary: null, error: null, hint: null, durationMs: null, lastSeq: 0,
}

type Action = { type: 'run'; run: Run } | { type: 'event'; event: RunEvent } | { type: 'reset' }

function upsertStep(steps: StepState[], name: string, patch: Partial<StepState>): StepState[] {
  const index = steps.findIndex((s) => s.name === name)
  if (index === -1) return [...steps, { name, status: 'pending', ...patch }]
  const next = [...steps]
  next[index] = { ...next[index], ...patch }
  return next
}

function reducer(state: RunState, action: Action): RunState {
  if (action.type === 'reset') return initial
  if (action.type === 'run') {
    const run = action.run
    return {
      ...state,
      run,
      status: run.status,
      outputs: run.outputs?.length ? run.outputs : state.outputs,
      summary: run.summary ?? state.summary,
      error: run.error ?? state.error,
      hint: run.error_hint ?? state.hint,
      durationMs: run.duration_ms ?? state.durationMs,
    }
  }
  const e = action.event
  // Les numéros de séquence sont croissants : tout ce qui est déjà vu (rejeu + direct) est ignoré.
  if (e.seq) {
    if (e.seq <= state.lastSeq) return state
    state = { ...state, lastSeq: e.seq }
  }
  switch (e.type) {
    case 'status':
      return { ...state, status: e.status }
    case 'plan':
      return { ...state, steps: e.steps.map((name) => state.steps.find((s) => s.name === name) ?? { name, status: 'pending' }) }
    case 'step':
      return { ...state, steps: upsertStep(state.steps, e.name, { status: e.status, duration: e.duration }) }
    case 'progress':
      return { ...state, progress: e.value, progressMessage: e.message ?? state.progressMessage }
    case 'log':
      return { ...state, logs: [...state.logs.slice(-1500), { id: state.logs.length ? state.logs[state.logs.length - 1].id + 1 : 1, level: e.level, message: e.message, ts: e.ts }] }
    case 'output':
      return state.outputs.some((o) => o.name === e.name) ? state : { ...state, outputs: [...state.outputs, { name: e.name, kind: e.kind, label: e.label, size: e.size }] }
    case 'table':
      return { ...state, tables: [...state.tables.filter((t) => t.title !== e.title), { title: e.title, columns: e.columns, rows: e.rows, total_rows: e.total_rows }] }
    case 'summary':
      return { ...state, summary: e.text }
    case 'result':
      return {
        ...state,
        status: e.status,
        error: e.error ?? null,
        hint: e.hint ?? null,
        summary: e.summary ?? state.summary,
        durationMs: e.duration_ms ?? state.durationMs,
        progress: e.status === 'success' ? 1 : state.progress,
        steps: e.status === 'success' ? state.steps.map((s) => (s.status === 'pending' ? { ...s, status: 'done' } : s)) : state.steps,
      }
    default:
      return state
  }
}

/** Suit une exécution : rejoue l'historique puis écoute le flux SSE en direct. */
export function useRunStream(runId: string, seed?: Run) {
  const [state, dispatch] = useReducer(reducer, initial, (s) => (seed ? reducer(s, { type: 'run', run: seed }) : s))

  useEffect(() => {
    dispatch({ type: 'reset' })
    if (seed && seed.id === runId) dispatch({ type: 'run', run: seed })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId])

  useEventSource(`/api/runs/${runId}/events`, (message, type) => {
    try {
      const payload = JSON.parse(message.data)
      if (type === 'run' || type === 'end') {
        if (payload) dispatch({ type: 'run', run: payload as Run })
      } else {
        dispatch({ type: 'event', event: payload as RunEvent })
      }
    } catch {
      /* message illisible : ignoré */
    }
  })

  const refresh = useCallback(() => api.getRun(runId).then((run) => dispatch({ type: 'run', run })), [runId])
  return { state, refresh }
}
