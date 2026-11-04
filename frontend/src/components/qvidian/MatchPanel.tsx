/**
 * Rapprochement calibré des questions déjà tombées : mesure de la calibration sur les anciens RFI (fiabilité par
 * tranche), seuil « même question », et essai d'une question (questions passées + texte Qvidian choisi).
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { RefreshCw, Search } from 'lucide-react'
import { texts } from '../../content/texts'
import { api } from '../../lib/api'
import type { MatchResult, MatchStatus } from '../../lib/types'
import { Button } from '../ui/Button'
import { TextInput } from '../ui/Field'

const Q = texts.qvidian

function pct(p: number) { return `${Math.round(p * 100)} %` }

export function MatchPanel({ fail }: { fail: (e: unknown) => void }) {
  const [st, setSt] = useState<MatchStatus | null>(null)
  const [q, setQ] = useState('')
  const [res, setRes] = useState<MatchResult | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { api.qvidian.matchStatus().then(setSt).catch(() => undefined) }, [])
  useEffect(() => {
    if (!st?.state.running) return
    const t = window.setInterval(() => { api.qvidian.matchStatus().then(setSt).catch(() => undefined) }, 2000)
    return () => window.clearInterval(t)
  }, [st?.state.running])
  const r = st?.stats?.report
  const ask = async () => {
    if (!q.trim()) return
    setBusy(true)
    try { setRes(await api.qvidian.match(q)) } catch (e) { fail(e) } finally { setBusy(false) }
  }
  return (
    <div className="flex flex-col gap-3">
      <p className="max-w-3xl text-sm font-semibold text-fg-2">{Q.matchLead}</p>
      {st?.stats && <p className="text-sm font-bold">{Q.matchStats(st.stats.questions, st.stats.distinct, st.stats.files)}</p>}
      {st?.state.running && <p className="text-xs font-bold" aria-live="polite">{st.state.message}</p>}
      {st?.state.error && <p className="text-xs font-bold text-danger">{st.state.error}</p>}
      {r ? (
        <div className="flex flex-col gap-2">
          <p className="text-sm font-semibold">{Q.matchCalib(r.ece, r.auc, r.pairs)}</p>
          <p className="text-sm font-semibold">{Q.matchThreshold(r.threshold, r.precision_at_threshold, r.recall_at_threshold)}</p>
          <div className="flex items-end gap-1" aria-label="Fiabilité : probabilité annoncée (trait) et taux observé (barre) par tranche">
            {r.reliability.map((b) => (
              <div key={b.from} className="flex w-8 flex-col items-center gap-0.5" title={`${pct(b.from)}–${pct(b.from + 0.1)} : annoncé ${pct(b.predicted)}, observé ${pct(b.observed)} (${b.n} couples)`}>
                <div className="relative h-16 w-5 rounded bg-fg/10">
                  <div className="absolute bottom-0 w-full rounded bg-mint-400" style={{ height: `${b.observed * 100}%` }} />
                  <div className="absolute w-full border-t-2 border-fg" style={{ bottom: `${b.predicted * 100}%` }} />
                </div>
                <span className="text-[0.6rem] font-bold text-fg-3">{Math.round(b.from * 100)}</span>
              </div>
            ))}
          </div>
        </div>
      ) : st && !st.state.running && <p className="text-sm font-semibold text-fg-2">{Q.matchNotTrained(st.state.reason || '—')}</p>}
      <div className="flex flex-wrap gap-2">
        <form className="flex min-w-[16rem] flex-1 gap-2" onSubmit={(e) => { e.preventDefault(); void ask() }}>
          <TextInput aria-label={Q.matchTry} placeholder={Q.matchTry} value={q} onChange={(e) => setQ(e.target.value)} />
          <Button type="submit" size="sm" variant="primary" loading={busy} icon={<Search size={14} />}>OK</Button>
        </form>
        <Button size="sm" variant="ghost" onClick={async () => { try { setSt(await api.qvidian.matchRebuild()) } catch (e) { fail(e) } }} icon={<RefreshCw size={14} />}>{Q.matchRebuild}</Button>
      </div>
      {res && (res.matches.length === 0 ? <p className="text-sm font-semibold text-fg-3">{Q.matchNone}</p> : (
        <div className="grid gap-3 lg:grid-cols-2">
          <ul className="flex flex-col gap-2">
            {res.matches.map((m, i) => (
              <li key={i} className="rounded-xl border-2 border-fg/20 p-3 text-sm">
                <p className="flex items-start gap-2">
                  <span className={`shrink-0 rounded-full px-2 text-xs font-bold ${res.threshold != null && m.p >= res.threshold ? 'bg-mint-400' : 'bg-card-3'}`}>{pct(m.p)}</span>
                  <span className="font-semibold">« {m.question} »</span>
                </p>
                <p className="mt-1 text-xs font-semibold text-fg-3">{m.files} RFI · {m.last || '—'}{m.why.length ? ` · ${m.why.join(' · ')}` : ''}{m.precise ? ' · relu par le pack Précis' : ''}</p>
              </li>
            ))}
          </ul>
          <ul className="flex flex-col gap-2">
            {res.answers.map((a) => (
              <li key={a.id} className="rounded-xl border-2 border-fg bg-sun-400/15 p-3 text-sm">
                <p className="font-bold"><Link to={`/qvidian/contenu/${a.id}`} className="hover:underline">#{a.id} · {a.title}</Link> <span className="text-xs">({pct(a.p)})</span></p>
                <p className="mt-1 line-clamp-3 text-xs font-semibold text-fg-2">{a.text}</p>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}
