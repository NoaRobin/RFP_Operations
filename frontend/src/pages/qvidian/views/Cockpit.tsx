/** Cockpit : santé, usage, niveaux des réponses (société / stratégie / fonds / part), thèmes, moteur et API. */
import { lazy, Suspense, useEffect, useState } from 'react'
import { useReducedMotion } from '../../../motion/useReducedMotion'
import { Link, useNavigate } from 'react-router-dom'
import { Cpu, HeartPulse, Search, Sparkles } from 'lucide-react'
import { Bar, Kpi, LevelBadge } from '../../../components/qvidian/Bits'
import { HistoryPanel } from '../../../components/qvidian/HistoryPanel'
import { Button } from '../../../components/ui/Button'
import { texts } from '../../../content/texts'
import { api } from '../../../lib/api'
import type { QvidianApiStats, QvidianOverview } from '../../../lib/types'
import { healthScore, useQvidian } from '../context'

const Constellation = lazy(() => import('../../../components/qviapi/Constellation'))
const webgl = () => { try { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')) } catch { return false } }
const Q = texts.qvidian
const SCOPE_TONE: Record<string, string> = { societe: 'bg-magic-400', strategie: 'bg-sun-400', fonds: 'bg-mint-400', part: 'bg-bubble-400', generique: 'bg-card-3' }

export function Cockpit() {
  const { audit, status } = useQvidian()
  const navigate = useNavigate()
  const [ov, setOv] = useState<QvidianOverview | null>(null)
  const [stats, setStats] = useState<QvidianApiStats | null>(null)
  const [q, setQ] = useState('')
  const reduced = useReducedMotion()
  const show3d = !reduced && webgl()
  useEffect(() => {
    let alive = true
    const load = (retry: number) => api.qvidian.overview().then((o) => alive && setOv(o))
      .catch(() => alive && retry > 0 && window.setTimeout(() => load(retry - 1), 1500))
    load(2)
    api.qvidian.apiStats().then((s) => alive && setStats(s)).catch(() => undefined)
    return () => { alive = false }
  }, [status?.snapshot.synced_at])
  if (!audit) return null
  const score = healthScore(audit)
  const tone = score >= 80 ? 'bg-mint-400' : score >= 60 ? 'bg-sun-400' : 'bg-bubble-400'
  const scopes = ov?.facets.scope ?? []
  const maxScope = Math.max(1, ...scopes.map((s) => s.count))
  const tel = stats?.telemetry
  return (
    <div className="flex flex-col gap-6">
      <header data-enter>
        <h1 className="text-[clamp(1.8rem,3.6vw,2.8rem)] font-bold leading-none">{Q.cockpitTitle}</h1>
        <form className="mt-4 flex max-w-3xl gap-2" onSubmit={(e) => { e.preventDefault(); navigate(`/qvidian/recherche?q=${encodeURIComponent(q)}`) }}>
          <div className="relative flex-1">
            <Search size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-fg-3" aria-hidden="true" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={Q.searchPlaceholder} aria-label={Q.goSearch}
              className="h-12 w-full rounded-2xl border-[2.5px] border-fg bg-card pl-11 pr-3 font-semibold placeholder:font-normal placeholder:text-fg-3 focus:shadow-[4px_4px_0_0_var(--color-magic-500)] focus:outline-none" />
          </div>
          <Button type="submit" variant="primary" icon={<Sparkles size={16} />}>{Q.goSearch}</Button>
        </form>
      </header>

      {show3d && audit.items.length > 0 && (
        <section data-enter className="relative overflow-hidden rounded-[var(--radius-card)] border-2 border-fg bg-card" aria-label={texts.qviapi.constellation}>
          <Suspense fallback={<div className="h-64" />}><Constellation items={audit.items} /></Suspense>
          <p className="absolute bottom-3 left-4 max-w-md text-xs text-fg-3">{texts.qviapi.constellationLead(audit.items.length)}</p>
        </section>
      )}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <section data-enter className="flex flex-col gap-4">
          <div className="flex items-center gap-5 rounded-[var(--radius-card)] border-[2.5px] border-fg bg-card p-5 shadow-[var(--shadow-pop)]">
            <div className={`grid size-28 shrink-0 place-items-center rounded-full border-[3px] border-fg ${tone}`}>
              <span className="font-display text-4xl font-bold tabular-nums">{score}</span>
            </div>
            <div>
              <p className="font-display text-2xl font-semibold">{Q.healthTitle}</p>
              <p className="mt-1 text-sm font-semibold text-fg-2">{Q.healthLead(audit.contents - audit.with_issues, audit.contents)}</p>
              <Link to="/qvidian/sante" className="mt-2 inline-flex items-center gap-1 text-sm font-bold text-magic-300 underline"><HeartPulse size={14} aria-hidden="true" />{Q.goMap}</Link>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Kpi label={Q.kpiContents} value={audit.contents} />
            <Kpi label={Q.kpiIssues} value={audit.with_issues} />
            <Kpi label={Q.kpiUses} value={ov ? ov.uses_total.toLocaleString('fr-FR') : '—'} />
            <Kpi label={Q.kpiNever} value={ov ? ov.never_used : '—'} />
          </div>
          <div className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-5">
            <h2 className="flex items-center gap-2 text-lg"><Cpu size={17} aria-hidden="true" />{Q.engineCard}</h2>
            <p className="mt-1 text-sm font-semibold">{ov?.engine.encoder ? Q.engineNeural(ov.engine.encoder, ov.engine.reranker) : Q.engineLexical}</p>
            <p className="text-xs font-semibold text-fg-3">{ov ? `${ov.engine.documents} contenus indexés · ${ov.engine.funds.length} fonds reconnus` : ''}</p>
            {!ov?.engine.encoder && <p className="mt-2 text-xs font-semibold text-fg-2">{Q.engineHint}</p>}
            {tel && tel.calls > 0 && (
              <p className="mt-3 text-xs font-bold text-fg-2">{Q.apiCard} : {tel.calls} appels · p95 {tel.p95_ms} ms · cache {Math.round(tel.cache_rate * 100)} % · erreurs {Math.round(tel.error_rate * 100)} %</p>
            )}
            <Link to="/qvidian/api" className="mt-2 inline-block text-sm font-bold text-magic-300 underline">{Q.nav.api}</Link>
          </div>
        </section>

        <section data-enter className="flex flex-col gap-4">
          <div className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-5">
            <h2 className="text-lg">{Q.byScope}</h2>
            <p className="text-xs font-semibold text-fg-3">{Q.byScopeLead}</p>
            <ul className="mt-3 flex flex-col gap-2">
              {scopes.map((s) => (
                <li key={s.value}>
                  <Link to={`/qvidian/recherche`} state={{ scope: s.value }} className="flex items-center gap-3 rounded-lg px-1 hover:bg-card-2">
                    <span className="w-24 shrink-0 text-sm font-bold">{s.label}</span>
                    <Bar value={s.count / maxScope} tone={SCOPE_TONE[s.value]} />
                    <span className="w-10 text-right text-sm font-bold tabular-nums">{s.count}</span>
                  </Link>
                </li>
              ))}
            </ul>
            <div className="mt-4 flex flex-wrap gap-1.5">
              {(ov?.facets.theme ?? []).map((t) => (
                <Link key={t.value} to={`/qvidian/recherche?q=${encodeURIComponent(t.label ?? t.value)}`} className="rounded-full border-2 border-fg/30 px-2.5 py-0.5 text-xs font-bold hover:border-fg">
                  {t.label} <span className="text-fg-3">{t.count}</span>
                </Link>
              ))}
            </div>
          </div>
          <HistoryPanel compact />
          <div className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-5">
            <h2 className="text-lg">{Q.topUsed}</h2>
            <ol className="mt-3 flex flex-col gap-2">
              {(ov?.top_used ?? []).map((c, i) => (
                <li key={c.id} className="flex items-center gap-3">
                  <span className="grid size-7 shrink-0 place-items-center rounded-full border-2 border-fg bg-sun-400 text-xs font-bold">{i + 1}</span>
                  <Link to={`/qvidian/contenu/${c.id}`} className="min-w-0 flex-1 truncate text-sm font-semibold hover:underline">{c.title}</Link>
                  <LevelBadge level={c.level} compact />
                  <span className="w-14 text-right text-xs font-bold tabular-nums">{Q.uses(c.times_used)}</span>
                </li>
              ))}
            </ol>
          </div>
        </section>
      </div>
    </div>
  )
}
