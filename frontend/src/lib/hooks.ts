import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from './api'

export interface AsyncState<T> {
  data: T | undefined
  error: ApiError | undefined
  loading: boolean
  reload: () => void
  setData: (updater: T | ((prev: T | undefined) => T)) => void
}

/** Petit hook de chargement : suffisant pour une application interne, sans dépendance supplémentaire. */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setDataState] = useState<T>()
  const [error, setError] = useState<ApiError>()
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)
  const loaderRef = useRef(loader)
  loaderRef.current = loader

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError(undefined)
    loaderRef
      .current()
      .then((value) => alive && setDataState(value))
      .catch((e) => alive && setError(e instanceof ApiError ? e : new ApiError(String(e))))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  const setData = useCallback((updater: T | ((prev: T | undefined) => T)) => {
    setDataState((prev) => (typeof updater === 'function' ? (updater as (p: T | undefined) => T)(prev) : updater))
  }, [])
  return { data, error, loading, reload, setData }
}

/** Abonnement SSE avec reconnexion automatique gérée par EventSource. */
export function useEventSource(url: string | null, onMessage: (event: MessageEvent, type: string) => void) {
  const handler = useRef(onMessage)
  handler.current = onMessage
  useEffect(() => {
    if (!url) return
    const source = new EventSource(url)
    const types = ['message', 'run', 'end']
    const listeners = types.map((type) => {
      const listener = (event: MessageEvent) => {
        handler.current(event, type)
        if (type === 'end') source.close()
      }
      source.addEventListener(type, listener as EventListener)
      return [type, listener] as const
    })
    return () => {
      listeners.forEach(([type, listener]) => source.removeEventListener(type, listener as EventListener))
      source.close()
    }
  }, [url])
}

/** Raccourci clavier global (ignoré quand on tape dans un champ). */
export function useHotkey(key: string, callback: (e: KeyboardEvent) => void) {
  const cb = useRef(callback)
  cb.current = callback
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      if (target.closest('input, textarea, select, [contenteditable="true"]')) return
      if (e.key === key && !e.metaKey && !e.ctrlKey && !e.altKey) cb.current(e)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [key])
}

/** Messages de chargement tournants. */
export function useRotatingMessage(messages: readonly string[], interval = 2200): string {
  const [index, setIndex] = useState(() => Math.floor(Math.random() * messages.length))
  useEffect(() => {
    const id = window.setInterval(() => setIndex((i) => (i + 1) % messages.length), interval)
    return () => window.clearInterval(id)
  }, [messages, interval])
  return messages[index]
}
