/**
 * État partagé de la section Qvidian : statut de connexion, carte des erreurs, journal, sélection (gardée d'une vue
 * à l'autre et pendant la session), synchronisation suivie jusqu'à la fin.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useToast } from '../../components/ui/Toast'
import { texts } from '../../content/texts'
import { api, ApiError } from '../../lib/api'
import type { QvidianAudit, QvidianJournalEntry, QvidianStatus } from '../../lib/types'

interface QvidianState {
  status: QvidianStatus | null
  audit: QvidianAudit | null
  journal: QvidianJournalEntry[]
  error: ApiError | null
  depth: number
  setDepth: (n: number) => void
  selected: Set<number>
  toggle: (id: number, on?: boolean) => void
  select: (ids: number[]) => void
  clear: () => void
  reload: () => Promise<void>
  sync: (kind?: 'auto' | 'full' | 'delta') => Promise<void>
  fail: (e: unknown) => void
}

const Ctx = createContext<QvidianState | null>(null)
// Dernier état connu, gardé hors du composant : revenir sur la section affiche tout de suite, puis rafraîchit en fond
const memo: { status: QvidianStatus | null; audit: QvidianAudit | null; journal: QvidianJournalEntry[] } = { status: null, audit: null, journal: [] }
const KEY = 'qvidian.selection'

function initialSelection(): Set<number> {
  try {
    return new Set((JSON.parse(sessionStorage.getItem(KEY) || '[]') as number[]).filter(Number.isFinite))
  } catch {
    return new Set()
  }
}

export function QvidianProvider({ children }: { children: ReactNode }) {
  const toast = useToast()
  const [status, setStatus] = useState<QvidianStatus | null>(memo.status)
  const [audit, setAudit] = useState<QvidianAudit | null>(memo.audit)
  const [journal, setJournal] = useState<QvidianJournalEntry[]>(memo.journal)
  const [error, setError] = useState<ApiError | null>(null)
  const [depth, setDepth] = useState(2)
  const [selected, setSelected] = useState<Set<number>>(initialSelection)

  useEffect(() => {
    try { sessionStorage.setItem(KEY, JSON.stringify([...selected])) } catch { /* stockage indisponible : sélection en mémoire */ }
  }, [selected])

  const fail = useCallback((e: unknown) => {
    toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
  }, [toast])

  const reload = useCallback(async () => {
    // Chacun s'affiche dès qu'il arrive : l'état de connexion (instantané) n'attend jamais la carte des erreurs
    const failed = (e: unknown) => setError(e instanceof ApiError ? e : new ApiError(String(e)))
    const s = api.qvidian.status().then((v) => { memo.status = v; setStatus(v); setError(null) }, failed)
    const a = api.qvidian.audit(depth).then((v) => { memo.audit = v; setAudit(v) }, failed)
    const j = api.qvidian.journal().then((v) => { memo.journal = v; setJournal(v) }, () => undefined)
    await Promise.all([s, a, j])
  }, [depth])

  useEffect(() => { void reload() }, [reload])

  // Synchronisation en cours : on suit l'avancement, puis tout est relu
  useEffect(() => {
    if (!status?.sync.running) return
    const t = window.setInterval(async () => {
      try {
        const s = await api.qvidian.status()
        setStatus(s)
        if (!s.sync.running) {
          window.clearInterval(t)
          void reload()
        }
      } catch { /* réessayé au tour suivant */ }
    }, 1200)
    return () => window.clearInterval(t)
  }, [status?.sync.running, reload])

  const sync = useCallback(async (kind: 'auto' | 'full' | 'delta' = 'auto') => {
    try {
      await api.qvidian.sync(kind)
      setStatus(await api.qvidian.status())
    } catch (e) { fail(e) }
  }, [fail])

  const value = useMemo<QvidianState>(() => ({
    status, audit, journal, error, depth, setDepth, selected, fail, reload, sync,
    toggle: (id, on) => setSelected((s) => {
      const n = new Set(s)
      if (on ?? !n.has(id)) n.add(id)
      else n.delete(id)
      return n
    }),
    select: (ids) => setSelected((s) => new Set([...s, ...ids])),
    clear: () => setSelected(new Set()),
  }), [status, audit, journal, error, depth, selected, fail, reload, sync])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useQvidian(): QvidianState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useQvidian hors de QvidianProvider')
  return v
}

/** Santé : part des contenus sans défaut, pondérée par la gravité. */
export function healthScore(audit: QvidianAudit): number {
  if (!audit.contents) return 100
  const weight: Record<string, number> = { haute: 1, moyenne: 0.5, basse: 0.15 }
  const penalty = audit.items.reduce((sum, it) => sum + Math.min(1, it.issues.reduce((m, i) => Math.max(m, weight[i.severity] ?? 0.3), 0)), 0)
  return Math.round(100 * (1 - penalty / audit.contents))
}
