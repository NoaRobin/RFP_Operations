/** « Appris des anciens RFI » : questions passées rapprochées des textes Qvidian choisis, et relecture à la demande. */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { History, RefreshCw } from 'lucide-react'
import { texts } from '../../content/texts'
import { api } from '../../lib/api'
import type { QvidianHistorySummary } from '../../lib/types'
import { Button } from '../ui/Button'

const Q = texts.qvidian

export function HistoryPanel({ compact = false }: { compact?: boolean }) {
  const [h, setH] = useState<QvidianHistorySummary | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { api.qvidian.history().then(setH).catch(() => setH(null)) }, [])
  const rebuild = async () => {
    setBusy(true)
    try { setH(await api.qvidian.historyRebuild()) } finally { setBusy(false) }
  }
  return (
    <section className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-5">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="flex items-center gap-2 text-lg"><History size={17} aria-hidden="true" />{Q.historyTitle}</h2>
        <Button size="sm" variant="ghost" className="ml-auto" onClick={rebuild} loading={busy} icon={<RefreshCw size={14} />}>{Q.historyRebuild}</Button>
      </div>
      <p className="mt-1 text-xs font-semibold text-fg-2">{Q.historyLead}</p>
      {h && <p className="mt-2 text-sm font-bold">{Q.historyStats(h.links, h.contents, h.files)}{h.built_at ? ` · ${h.built_at.replace('T', ' ').slice(0, 16)}` : ''}</p>}
      {h?.state.error && <p className="text-xs font-bold text-danger">{h.state.error}</p>}
      <ol className="mt-3 flex flex-col gap-2">
        {(h?.top ?? []).slice(0, compact ? 5 : 12).map((t) => (
          <li key={t.id} className="text-sm">
            <span className="mr-2 rounded-full bg-sun-400 px-2 text-xs font-bold tabular-nums">{t.files}</span>
            <Link to={`/qvidian/contenu/${t.id}`} className="font-semibold hover:underline">{t.title}</Link>
            <span className="block truncate pl-8 text-xs font-semibold text-fg-3">« {t.questions.slice(0, 2).join(' » · « ')} »</span>
          </li>
        ))}
      </ol>
    </section>
  )
}
