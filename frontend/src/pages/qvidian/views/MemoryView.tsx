/**
 * Mémoire des réponses (Pit Stop) : ce que l'équipe a déjà répondu, et ce que cela vaut.
 * Cadrans du stand, réutilisation dans le temps, puis trois listes d'action : textes à créer (questions récurrentes
 * sans texte Qvidian), textes piliers, textes à rafraîchir en priorité. Tout mène à une fiche.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Gauge } from '../../../components/pitstop/Gauge'
import { ErrorState, Loading } from '../../../components/ui/States'
import { texts } from '../../../content/texts'
import { api, ApiError } from '../../../lib/api'
import type { MemoryCard, QvidianMemory } from '../../../lib/types'
import { Mechanic } from '../../../universe/Mascots'

const M = texts.pitstop

function Timeline({ data }: { data: QvidianMemory['timeline'] }) {
  if (!data.length) return <p className="text-sm font-semibold text-fg-3">{M.noTimeline}</p>
  const max = Math.max(...data.map((d) => d.answers), 1)
  return (
    <div className="flex h-36 items-end gap-1.5" role="img" aria-label={M.timelineAria(data.reduce((a, d) => a + d.answers, 0), data.length)}>
      {data.map((d) => (
        <div key={d.month} className="group flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1">
          <span className="font-mono text-[0.65rem] font-bold text-fg-3 opacity-0 group-hover:opacity-100">{d.answers}</span>
          <div className="w-full max-w-16 rounded-t-md border-2 border-fg bg-magic-500" style={{ height: `${Math.max(6, (80 * d.answers) / max)}%` }} title={`${d.month} : ${d.answers}`} />
          <span className="font-mono text-[0.6rem] text-fg-3">{d.month.slice(2).replace('-', '/')}</span>
        </div>
      ))}
    </div>
  )
}

function ContentRow({ c, extra }: { c: MemoryCard; extra?: string }) {
  return (
    <li className="border-t border-fg/10 py-2.5 first:border-t-0">
      <Link to={`/qvidian/contenu/${c.id}`} className="font-semibold hover:underline">{c.title}</Link>
      <p className="text-xs font-semibold text-fg-3">
        {M.inRfis(c.rfis)}{c.last_rfi ? ` · ${M.lastRfi(c.last_rfi)}` : ''}{extra ? ` · ${extra}` : ''}
      </p>
      {c.questions[0] && <p className="mt-0.5 line-clamp-1 text-xs text-fg-2">« {c.questions[0]} »</p>}
    </li>
  )
}

export function MemoryView() {
  const [m, setM] = useState<QvidianMemory | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  useEffect(() => { api.qvidian.memory().then(setM).catch((e) => setError(e instanceof ApiError ? e : new ApiError(String(e)))) }, [])
  if (error) return <ErrorState error={error} />
  if (!m) return <Loading />
  const b = m.bank
  return (
    <div className="flex flex-col gap-5">
      <header data-enter className="flex flex-wrap items-end gap-4">
        <Mechanic className="size-20 shrink-0" />
        <div className="min-w-0 flex-1">
          <h1 className="text-[clamp(1.8rem,3.6vw,2.8rem)] font-bold leading-none">{M.memoryTitle}</h1>
          <p className="mt-2 max-w-2xl text-sm font-semibold text-fg-2">{M.memoryLead(m.rfis, m.links)}</p>
        </div>
      </header>

      <section data-enter className="pit-scan grid grid-cols-2 gap-4 rounded-[var(--radius-card)] border-[2.5px] border-fg bg-card p-5 shadow-[5px_5px_0_0_var(--color-fg)] md:grid-cols-4" aria-label={M.dials}>
        <Gauge value={b.rate} label={M.gCoverage} hint={b.distinct ? M.gCoverageHint(b.covered, b.distinct) : M.gNoBank} />
        <Gauge value={m.reuse_rate} label={M.gReuse} hint={M.gReuseHint(m.texts_reused, m.library)} />
        <Gauge value={m.rfis ? Math.min(1, m.rfis / 400) : 0} display={String(m.rfis)} label={M.gRfis} hint={M.gRfisHint} />
        <Gauge value={m.texts_reused ? 1 - m.stale.length / Math.max(1, m.texts_reused) : null} label={M.gFresh} hint={M.gFreshHint(m.stale.length)} />
      </section>

      <section data-enter className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-5">
        <h2 className="text-lg">{M.timelineTitle}</h2>
        <p className="mb-3 text-xs font-semibold text-fg-3">{M.timelineLead}</p>
        <Timeline data={m.timeline} />
      </section>

      <div className="grid gap-5 lg:grid-cols-3">
        <section data-enter className="rounded-[var(--radius-card)] border-[2.5px] border-fg bg-bubble-400/10 p-5" aria-label={M.toCreate}>
          <h2 className="text-lg">{M.toCreate} ({b.orphans.length})</h2>
          <p className="text-xs font-semibold text-fg-3">{M.toCreateLead}</p>
          {b.orphans.length === 0 ? <p className="mt-3 text-sm font-semibold">{M.toCreateNone}</p> : (
            <ul className="mt-2">
              {b.orphans.map((o) => (
                <li key={o.question} className="border-t border-fg/10 py-2.5 first:border-t-0">
                  <p className="font-semibold">« {o.question} »</p>
                  <p className="text-xs font-semibold text-fg-3">{M.inRfis(o.rfis)}{o.last ? ` · ${M.lastRfi(o.last)}` : ''}</p>
                  {o.answers[0] && <p className="mt-1 line-clamp-2 text-xs text-fg-2">{M.pastAnswer} {o.answers[0]}</p>}
                  <Link to={`/qvidian/recherche?q=${encodeURIComponent(o.question)}`} className="mt-1 inline-block text-xs font-bold underline">{M.searchIt}</Link>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section data-enter className="rounded-[var(--radius-card)] border-[2.5px] border-fg bg-card p-5" aria-label={M.pillars}>
          <h2 className="text-lg">{M.pillars}</h2>
          <p className="text-xs font-semibold text-fg-3">{M.pillarsLead}</p>
          <ul className="mt-2">{m.pillars.map((c) => <ContentRow key={c.id} c={c} />)}</ul>
        </section>
        <section data-enter className="rounded-[var(--radius-card)] border-[2.5px] border-fg bg-sun-400/25 p-5" aria-label={M.stale}>
          <h2 className="text-lg">{M.stale} ({m.stale.length})</h2>
          <p className="text-xs font-semibold text-fg-3">{M.staleLead}</p>
          {m.stale.length === 0 ? <p className="mt-3 text-sm font-semibold">{M.staleNone}</p> : (
            <ul className="mt-2">{m.stale.map((c) => <ContentRow key={c.id} c={c} extra={c.expired ? M.expired : M.modifiedAgo(c.modified)} />)}</ul>
          )}
        </section>
      </div>

      {m.unused_total > 0 && (
        <details data-enter className="rounded-[var(--radius-card)] border-2 border-fg/30 bg-card p-5">
          <summary className="cursor-pointer font-display text-lg font-semibold">{M.unused(m.unused_total)}</summary>
          <p className="mt-1 text-xs font-semibold text-fg-3">{M.unusedLead}</p>
          <ul className="mt-2 columns-1 gap-6 md:columns-2">{m.unused.map((c) => <ContentRow key={c.id} c={c} />)}</ul>
        </details>
      )}
    </div>
  )
}
