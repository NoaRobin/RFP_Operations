/**
 * Merlin, au centre de tout : une seule question pour chercher partout (fonds et parts, réponses déjà données,
 * équipe à contacter), puis les trois univers et les outils. La recherche est la pièce maîtresse de la page.
 */
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowUpRight, IdCard, Search } from 'lucide-react'
import { texts } from '../content/texts'
import { api } from '../lib/api'
import type { AskPlan, FundEntry, MatchResult, QvidianMemory } from '../lib/types'
import { AppMark } from '../components/ui/AppMark'
import { Mascot, Wizard } from '../universe/Mascots'
import { UNIVERSES } from '../universe/universes'

const H = texts.hub

interface Found { funds: FundEntry[]; answers: MatchResult['answers']; who: AskPlan['teams'] }

export default function MerlinHub() {
  const navigate = useNavigate()
  const input = useRef<HTMLInputElement>(null)
  const [q, setQ] = useState('')
  const [found, setFound] = useState<Found | null>(null)
  const [memory, setMemory] = useState<QvidianMemory | null>(null)
  useEffect(() => { api.qvidian.memory().then(setMemory).catch(() => undefined) }, [])
  useEffect(() => {
    const text = q.trim()
    if (text.length < 2) { setFound(null); return }
    const t = window.setTimeout(async () => {
      const [funds, match, ask] = await Promise.all([
        api.rfi.funds(text).catch(() => [] as FundEntry[]),
        text.length >= 6 ? api.qvidian.match(text, 4).catch(() => null) : Promise.resolve(null),
        text.length >= 10 ? api.contacts.ask([text]).catch(() => null) : Promise.resolve(null),
      ])
      setFound({ funds: funds.slice(0, 5), answers: match?.answers.slice(0, 3) ?? [], who: ask?.teams.slice(0, 2) ?? [] })
    }, 220)
    return () => window.clearTimeout(t)
  }, [q])
  const go = () => {
    const isin = q.trim().toUpperCase()
    if (/^[A-Z]{2}[A-Z0-9]{9}\d$/.test(isin)) navigate(`/atelier/fonds/${isin}`)
    else if (q.trim()) navigate(`/qvidian/recherche?q=${encodeURIComponent(q.trim())}`)
  }
  const doors = [
    { u: UNIVERSES.rfp, stat: H.rfpStat, lead: H.rfpLead, items: H.rfpItems },
    { u: UNIVERSES.pitstop, stat: memory ? H.pitStat(Math.round(memory.reuse_rate * 100), memory.rfis) : H.pitStatNone, lead: H.pitLead, items: H.pitItems },
    { u: UNIVERSES.suivi, stat: H.suiviStat, lead: H.suiviLead, items: H.suiviItems },
  ]
  return (
    <div className="mx-auto flex w-[min(100%-2rem,82rem)] flex-col gap-8 pt-8 sm:pt-12">
      <section className="flex flex-col items-center gap-4 text-center sm:flex-row sm:items-end sm:text-left">
        <Wizard className="size-32 shrink-0 motion-safe:animate-[float_4s_var(--ease-in-out-premium)_infinite] sm:size-40" />
        <div className="relative rounded-[var(--radius-card)] border-[3px] border-fg bg-card px-6 py-5 shadow-[6px_6px_0_0_var(--color-fg)]">
          <span className="absolute -left-3 bottom-8 hidden size-6 rotate-45 border-b-[3px] border-l-[3px] border-fg bg-card sm:block" aria-hidden="true" />
          <h1 className="font-display text-[clamp(2.2rem,5vw,3.8rem)] font-bold leading-[0.95] tracking-tight">{H.title}</h1>
          <p className="mt-2 max-w-xl text-base font-semibold text-fg-2">{H.lead}</p>
        </div>
      </section>

      <section aria-label={H.universes} className="grid gap-6 lg:grid-cols-3">
        {doors.map(({ u, stat, lead, items }) => (
          <Link key={u.id} to={u.home}
            className="group relative flex min-h-[22rem] flex-col gap-4 overflow-hidden rounded-[2rem] border-[3px] border-fg bg-card p-6 shadow-[7px_7px_0_0_var(--color-fg)] transition-[transform,box-shadow] duration-[var(--duration-fast)] ease-[var(--ease-spring)] hover:-translate-y-1.5 hover:rotate-[-0.6deg] hover:shadow-[10px_10px_0_0_var(--color-fg)] focus-visible:-translate-y-1.5">
            <span className="absolute inset-x-0 top-0 h-28 border-b-[3px] border-fg" style={{ background: `color-mix(in srgb, ${u.accent} 55%, white)` }} aria-hidden="true" />
            <span className="relative flex items-end justify-between">
              {u.id === 'rfp' ? <AppMark className="size-24 transition-transform group-hover:-rotate-6" /> : <Mascot universe={u.id} className="size-28 transition-transform group-hover:-rotate-6" />}
              <ArrowUpRight size={26} className="mb-2 transition-transform group-hover:-translate-y-1 group-hover:translate-x-1" aria-hidden="true" />
            </span>
            <span>
              <span className="block font-display text-3xl font-bold leading-none">{u.id === 'rfp' ? H.rfpName : u.name}</span>
              {u.id !== 'rfp' && <span className="mt-1 block text-sm font-bold text-fg-3">{u.sub}</span>}
            </span>
            <span className="text-sm font-semibold text-fg-2">{lead}</span>
            <span className="flex flex-wrap gap-1.5">{items.map((x) => <span key={x} className="rounded-full border-2 border-fg/20 px-2 py-0.5 text-xs font-bold">{x}</span>)}</span>
            <span className="mt-auto font-mono text-sm font-bold">{stat}</span>
          </Link>
        ))}
      </section>

      <section className="rounded-[var(--radius-card)] border-2 border-dashed border-fg/30 p-5">
        <h2 className="text-lg">{H.orAsk}</h2>
        <form className="relative mt-2" role="search" onSubmit={(e) => { e.preventDefault(); go() }}>
          <Search size={20} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-fg-3" aria-hidden="true" />
          <input ref={input} value={q} onChange={(e) => setQ(e.target.value)} aria-label={H.searchLabel} placeholder={H.searchPlaceholder}
            className="h-14 w-full rounded-2xl border-[2.5px] border-fg bg-field pl-12 pr-4 font-semibold shadow-[4px_4px_0_0_var(--color-magic-500)] placeholder:font-normal placeholder:text-fg-3 focus:outline-none" />
        </form>
      </section>

      {found && (
        <section aria-live="polite" aria-label={H.results} className="-mt-4 grid gap-4 md:grid-cols-3">
          <div className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-4">
            <h2 className="flex items-center gap-2 text-base"><IdCard size={16} aria-hidden="true" />{H.funds}</h2>
            {found.funds.length === 0 ? <p className="mt-2 text-sm text-fg-3">{H.none}</p> : (
              <ul className="mt-2 flex flex-col gap-1.5">
                {found.funds.map((f) => (
                  <li key={f.pid}>
                    <p className="text-sm font-bold">{f.name}</p>
                    <p className="flex flex-wrap gap-1">{f.shares.slice(0, 4).map((s) => (
                      <Link key={s.isin} to={`/atelier/fonds/${s.isin}`} className="rounded-full bg-card-2 px-2 py-0.5 font-mono text-xs font-bold hover:bg-card-3">{s.isin}</Link>
                    ))}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-4">
            <h2 className="flex items-center gap-2 text-base"><Mascot universe="pitstop" className="size-5" />{H.answers}</h2>
            {found.answers.length === 0 ? <p className="mt-2 text-sm text-fg-3">{q.trim().length < 6 ? H.typeMore : H.none}</p> : (
              <ul className="mt-2 flex flex-col gap-2">
                {found.answers.map((a) => (
                  <li key={a.id}>
                    <Link to={`/qvidian/contenu/${a.id}`} className="text-sm font-bold hover:underline">{a.title}</Link>
                    <p className="text-xs font-semibold text-fg-3">{H.sameQuestion(Math.round(a.p * 100), a.files)}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-4">
            <h2 className="flex items-center gap-2 text-base"><AppMark className="size-5" />{H.who}</h2>
            {found.who.length === 0 ? <p className="mt-2 text-sm text-fg-3">{q.trim().length < 10 ? H.typeMore : H.none}</p> : (
              <ul className="mt-2 flex flex-col gap-1.5">
                {found.who.map((t) => <li key={t.team} className="text-sm"><span className="font-bold">{t.team}</span><span className="block text-xs text-fg-3">{t.people.join(', ')}</span></li>)}
              </ul>
            )}
          </div>
        </section>
      )}

    </div>
  )
}
