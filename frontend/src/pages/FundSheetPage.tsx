/**
 * Fiche fonds (Atelier) : un fonds, une part, toutes les données Product Info + JUMP lues par l'ontologie RFI, avec leur
 * source, à une date choisie ; export Excel. Chercher un fonds par son nom ou son ISIN.
 */
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Download, Search } from 'lucide-react'
import { ErrorState, Loading } from '../components/ui/States'
import { TextInput } from '../components/ui/Field'
import { texts } from '../content/texts'
import { api, ApiError } from '../lib/api'
import type { FundEntry, FundSheet } from '../lib/types'

const F = texts.fundSheet

export default function FundSheetPage() {
  const { isin } = useParams()
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [funds, setFunds] = useState<FundEntry[]>([])
  const [asOf, setAsOf] = useState('')
  const [sheet, setSheet] = useState<FundSheet | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [onlyFilled, setOnlyFilled] = useState(true)
  useEffect(() => {
    const t = window.setTimeout(() => { api.rfi.funds(q).then((f) => setFunds(f.slice(0, 12))).catch(() => setFunds([])) }, 200)
    return () => window.clearTimeout(t)
  }, [q])
  useEffect(() => {
    if (!isin) { setSheet(null); return }
    setSheet(null); setError(null)
    api.atelier.fundSheet(isin, asOf).then(setSheet).catch((e) => setError(e instanceof ApiError ? e : new ApiError(String(e))))
  }, [isin, asOf])
  const name = funds.find((f) => f.shares.some((s) => s.isin === isin))
  return (
    <div className="mx-auto grid w-[min(100%-2rem,82rem)] gap-6 pt-8 lg:grid-cols-[18rem_minmax(0,1fr)]">
      <aside className="flex flex-col gap-3 lg:sticky lg:top-36 lg:self-start" aria-label={F.pick}>
        <h1 className="font-display text-3xl font-bold leading-none">{F.title}</h1>
        <p className="text-sm font-semibold text-fg-2">{F.lead}</p>
        <label className="relative">
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-3" aria-hidden="true" />
          <TextInput value={q} onChange={(e) => setQ(e.target.value)} placeholder={F.search} aria-label={F.search} className="pl-9" />
        </label>
        <ul className="flex max-h-[55vh] flex-col gap-2 overflow-y-auto pr-1" data-lenis-prevent>
          {funds.map((f) => (
            <li key={f.pid} className="rounded-xl border-2 border-fg/20 bg-card p-2.5">
              <p className="text-sm font-bold leading-tight">{f.name}</p>
              <p className="mt-1 flex flex-wrap gap-1">
                {f.shares.map((s) => (
                  <button key={s.isin} onClick={() => navigate(`/atelier/fonds/${s.isin}`)} title={s.name}
                    className={`rounded-full border-2 px-2 py-0.5 font-mono text-xs font-bold ${s.isin === isin ? 'border-fg bg-sun-400' : 'border-transparent bg-card-2 hover:border-fg'}`}>{s.isin}</button>
                ))}
              </p>
            </li>
          ))}
        </ul>
      </aside>
      <section aria-live="polite">
        {!isin && <p className="rounded-[var(--radius-card)] border-2 border-dashed border-fg/30 p-8 text-center font-semibold text-fg-2">{F.empty}</p>}
        {error && <ErrorState error={error} />}
        {isin && !sheet && !error && <Loading />}
        {sheet && (
          <div className="flex flex-col gap-4">
            <header className="flex flex-wrap items-end gap-3 rounded-[var(--radius-card)] border-[2.5px] border-fg bg-card p-5 shadow-[5px_5px_0_0_var(--color-fg)]">
              <div className="min-w-0 flex-1">
                <p className="font-mono text-sm font-bold text-fg-3">{sheet.isin}</p>
                <h2 className="text-2xl leading-tight">{name?.name ?? F.share}</h2>
                <p className="mt-1 text-sm font-semibold text-fg-2">{F.filled(sheet.filled, sheet.total)}</p>
              </div>
              <label className="flex flex-col gap-1 text-xs font-bold">{F.asOf}
                <TextInput type="date" value={asOf || sheet.as_of} onChange={(e) => setAsOf(e.target.value)} />
              </label>
              <label className="flex items-center gap-2 text-sm font-bold">
                <input type="checkbox" checked={onlyFilled} onChange={(e) => setOnlyFilled(e.target.checked)} className="size-4" />{F.onlyFilled}
              </label>
              <a href={api.atelier.fundSheetXlsx(sheet.isin, asOf)} className="inline-flex items-center gap-2 rounded-full border-2 border-fg bg-sun-400 px-4 py-2 text-sm font-bold shadow-[2px_2px_0_0_var(--color-fg)]">
                <Download size={15} aria-hidden="true" />{F.export}
              </a>
            </header>
            <div className="columns-1 gap-4 xl:columns-2">
              {Object.entries(sheet.groups).map(([group, items]) => {
                const shown = items.filter((x) => !onlyFilled || x.has_value)
                if (!shown.length) return null
                return (
                  <section key={group} className="mb-4 break-inside-avoid rounded-[var(--radius-card)] border-2 border-fg bg-card p-4">
                    <h3 className="text-lg">{group} <span className="text-sm font-semibold text-fg-3">({shown.length})</span></h3>
                    <dl className="mt-2 grid grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] gap-x-3 gap-y-1.5 text-sm">
                      {shown.map((x) => (
                        <div key={x.id} className="contents">
                          <dt className="font-semibold text-fg-2" title={x.source}>{x.label}</dt>
                          <dd className={`break-words font-bold ${x.has_value ? '' : 'font-normal text-fg-3'}`} title={x.issues.join(' · ') || x.evidence}>{x.display || '—'}</dd>
                        </div>
                      ))}
                    </dl>
                  </section>
                )
              })}
            </div>
            <p className="text-xs font-semibold text-fg-3">{F.note} <Link to="/atelier" className="underline">{F.toAtelier}</Link></p>
          </div>
        )}
      </section>
    </div>
  )
}
