/**
 * Merlin, au centre de tout : une seule question pour chercher partout (fonds et parts, réponses déjà données,
 * équipe à contacter), puis les trois univers et les outils. La recherche est la pièce maîtresse de la page.
 */
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowUpRight, FileSpreadsheet, IdCard, Search, Tags } from 'lucide-react'
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
  useEffect(() => { input.current?.focus(); api.qvidian.memory().then(setMemory).catch(() => undefined) }, [])
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
    { u: UNIVERSES.rfp, stat: H.rfpStat, lead: H.rfpLead },
    { u: UNIVERSES.pitstop, stat: memory ? H.pitStat(Math.round(memory.reuse_rate * 100), memory.rfis) : H.pitStatNone, lead: H.pitLead },
    { u: UNIVERSES.suivi, stat: H.suiviStat, lead: H.suiviLead },
  ]
  return (
    <div className="mx-auto flex w-[min(100%-2rem,82rem)] flex-col gap-10 pt-8 sm:pt-12">
      <section className="grid items-center gap-6 md:grid-cols-[auto_minmax(0,1fr)]">
        <Wizard className="mx-auto size-36 motion-safe:animate-[float_4s_var(--ease-in-out-premium)_infinite] sm:size-44" />
        <div>
          <h1 className="font-display text-[clamp(2.4rem,5.5vw,4.4rem)] font-bold leading-[0.95] tracking-tight">{H.title}</h1>
          <p className="mt-3 max-w-xl text-base font-semibold text-fg-2">{H.lead}</p>
          <form className="relative mt-5" role="search" onSubmit={(e) => { e.preventDefault(); go() }}>
            <Search size={22} className="pointer-events-none absolute left-5 top-1/2 -translate-y-1/2 text-fg-3" aria-hidden="true" />
            <input ref={input} value={q} onChange={(e) => setQ(e.target.value)} aria-label={H.searchLabel} placeholder={H.searchPlaceholder}
              className="h-16 w-full rounded-[1.25rem] border-[3px] border-fg bg-field pl-14 pr-5 text-lg font-semibold shadow-[6px_6px_0_0_var(--color-magic-500)] placeholder:font-normal placeholder:text-fg-3 focus:shadow-[6px_6px_0_0_var(--color-fg)] focus:outline-none" />
          </form>
        </div>
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

      <section aria-label={H.universes} className="grid gap-5 md:grid-cols-3">
        {doors.map(({ u, stat, lead }) => (
          <Link key={u.id} to={u.home}
            className="group relative flex flex-col gap-3 overflow-hidden rounded-[var(--radius-card)] border-[3px] border-fg bg-card p-5 shadow-[5px_5px_0_0_var(--color-fg)] transition-[transform,box-shadow] duration-[var(--duration-fast)] hover:-translate-y-1 hover:shadow-[8px_8px_0_0_var(--color-fg)]">
            <span className="absolute inset-x-0 top-0 h-3 border-b-[3px] border-fg" style={{ background: u.accent }} aria-hidden="true" />
            <span className="mt-2 flex items-center gap-3">
              {u.id === 'rfp' ? <AppMark className="size-14" /> : <Mascot universe={u.id} className="size-16" />}
              <span>
                <span className="block font-display text-2xl font-bold leading-none">{u.name}</span>
                <span className="text-sm font-semibold text-fg-3">{u.sub}</span>
              </span>
              <ArrowUpRight size={20} className="ml-auto transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" aria-hidden="true" />
            </span>
            <span className="text-sm font-semibold text-fg-2">{lead}</span>
            <span className="mt-auto font-mono text-sm font-bold">{stat}</span>
          </Link>
        ))}
      </section>

      <section aria-label={H.tools}>
        <h2 className="text-xl">{H.tools}</h2>
        <div className="mt-3 grid gap-4 sm:grid-cols-3">
          {[
            { to: '/atelier/fonds', icon: IdCard, title: H.toolSheet, lead: H.toolSheetLead },
            { to: '/atelier', icon: FileSpreadsheet, title: H.toolAtelier, lead: H.toolAtelierLead },
            { to: '/merge-codes', icon: Tags, title: H.toolMerge, lead: H.toolMergeLead },
          ].map(({ to, icon: Icon, title, lead }) => (
            <Link key={to} to={to} className="flex items-start gap-3 rounded-2xl border-2 border-fg bg-card-2 p-4 transition-colors hover:bg-card-3">
              <Icon size={22} className="mt-0.5 shrink-0" aria-hidden="true" />
              <span><span className="block font-display text-lg font-semibold">{title}</span><span className="text-sm text-fg-2">{lead}</span></span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  )
}
