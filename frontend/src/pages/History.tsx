import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CalendarClock } from 'lucide-react'
import { EmptyState, ErrorState, Loading } from '../components/ui/States'
import { StatusPill } from '../components/ui/StatusPill'
import { texts } from '../content/texts'
import { api } from '../lib/api'
import { formatDateTime, formatDuration } from '../lib/format'
import { useAsync } from '../lib/hooks'
import type { RunStatus } from '../lib/types'

const FILTERS: (RunStatus | '')[] = ['', 'running', 'success', 'error', 'cancelled']

export default function HistoryPage() {
  const [status, setStatus] = useState<RunStatus | ''>('')
  const { data, error, loading, reload } = useAsync(() => api.runs(`?limit=200${status ? `&status=${status}` : ''}`), [status])

  return (
    <div className="mx-auto w-[min(100%-2rem,82rem)] pt-16">
      <p className="eyebrow">{texts.history.eyebrow}</p>
      <h1 className="mt-4 text-[clamp(2.5rem,6vw,4.5rem)] font-light leading-none">{texts.history.title}</h1>

      <div role="group" aria-label="Filtrer par statut" className="mt-8 flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button key={f || 'all'} onClick={() => setStatus(f)} aria-pressed={status === f}
            className={`rounded-full border px-4 py-2 text-sm transition-colors ${status === f ? 'border-champagne-400/70 bg-champagne-400/15 text-champagne-200' : 'border-line-strong text-mist hover:text-ivory'}`}>
            {f ? texts.run.status[f] : texts.history.filterAll}
          </button>
        ))}
      </div>

      {error && <ErrorState error={error} onRetry={reload} />}
      {loading && !data && <Loading />}
      {data && data.length === 0 && <EmptyState title={texts.history.empty} />}
      {data && data.length > 0 && (
        <div className="mt-6 glass overflow-x-auto rounded-[var(--radius-card)]">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-champagne-300">
                {Object.values(texts.history.columns).map((c) => <th key={c} scope="col" className="border-b hairline px-5 py-3 font-semibold">{c}</th>)}
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id} className="hover:bg-white/[0.03]">
                  <td className="whitespace-nowrap border-b hairline px-5 py-3 text-mist">{formatDateTime(r.created_at)}</td>
                  <td className="border-b hairline px-5 py-3">
                    <Link to={`/executions/${r.id}`} className="font-medium text-ivory hover:text-champagne-200">{r.target_name}</Link>
                    {r.trigger === 'schedule' && <span className="ml-2 inline-flex items-center gap-1 text-xs text-haze"><CalendarClock size={12} aria-hidden="true" />{texts.history.scheduled}</span>}
                  </td>
                  <td className="border-b hairline px-5 py-3 text-mist">{r.user}</td>
                  <td className="border-b hairline px-5 py-3"><StatusPill status={r.status} /></td>
                  <td className="whitespace-nowrap border-b hairline px-5 py-3 text-haze tabular-nums">{formatDuration(r.duration_ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
