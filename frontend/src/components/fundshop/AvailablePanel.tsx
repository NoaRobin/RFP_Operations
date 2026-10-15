/**
 * « Ce que le site propose pour cette part » : la rubrique Téléchargements du site, lue par l'app. On coche ce qu'on veut ;
 * pour les reportings, « Mois précédent » (en boucle) ou un mois réellement publié. Impossible de demander ce qui n'existe pas.
 */
import { useEffect, useState } from 'react'
import { ExternalLink, Loader2, Plus, X } from 'lucide-react'
import { Button } from '../ui/Button'
import { texts } from '../../content/texts'
import { api, ApiError } from '../../lib/api'
import type { FundShopAvailable } from '../../lib/types'

const T = texts.fundshop

export interface Pick { kind: string; month: string }

export function AvailablePanel({ isin, fund, part, existing, onAdd, onClose }: {
  isin: string; fund: string; part: string; existing: Pick[]
  onAdd: (picks: Pick[], fund: string, part: string) => void; onClose: () => void
}) {
  const [data, setData] = useState<FundShopAvailable | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [chosen, setChosen] = useState<Record<string, string | null>>({})  // type → mois (« » sans objet, « M-1 », « 2026-08 »)

  useEffect(() => {
    setData(null); setError(null)
    api.fundshop.available(isin, fund, part).then((d) => {
      setData(d)
      // présélection raisonnable : DIC, prospectus, reporting du mois précédent
      const pre: Record<string, string | null> = {}
      for (const doc of d.documents) {
        if (doc.kind === 'dic' || doc.kind === 'prospectus') pre[doc.kind] = ''
        if (doc.kind === 'reporting mensuel') pre[doc.kind] = 'M-1'
      }
      setChosen(pre)
    }).catch((e) => setError(e instanceof ApiError ? e.message : texts.errors.generic))
  }, [isin, fund, part])

  const has = (kind: string, month: string) => existing.some((x) => x.kind === kind && x.month === month)
  const picks = Object.entries(chosen).filter(([, m]) => m !== null && m !== undefined).map(([kind, month]) => ({ kind, month: month as string }))
    .filter((p) => !has(p.kind, p.month))

  return (
    <div className="mt-3 rounded-2xl border-[2.5px] border-fg bg-card p-4 shadow-[var(--shadow-pop)]">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-display text-lg font-semibold">{T.availableTitle(data?.part || part || isin)}</p>
          <p className="text-xs font-semibold text-fg-3">{data?.fund || fund} · {isin}
            {data?.page && <> · <a href={data.page} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 underline">{T.sitePage}<ExternalLink size={10} aria-hidden="true" /></a></>}</p>
        </div>
        <button onClick={onClose} aria-label={texts.common.close} className="rounded-full border-2 border-fg/30 p-1 hover:border-fg"><X size={14} /></button>
      </div>
      {!data && !error && <p className="mt-3 flex items-center gap-2 text-sm font-semibold text-fg-2"><Loader2 size={15} className="motion-safe:animate-spin" />{T.reading}</p>}
      {error && <p className="mt-3 text-sm font-semibold text-danger">{error}</p>}
      {data?.problem && (
        <div className="mt-3 text-sm font-semibold">
          <p className="font-bold text-danger">{data.problem.title}</p>
          <p className="text-fg-2">{data.problem.why}</p>
          <p><span className="font-bold">{T.whatToDo}</span> {data.problem.fix}</p>
        </div>
      )}
      {data && data.documents.length > 0 && (
        <>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {data.documents.map((doc) => {
              const value = chosen[doc.kind]
              const on = value !== null && value !== undefined
              return (
                <li key={doc.kind} className={`rounded-xl border-2 p-2.5 ${on ? 'border-fg bg-sun-400/30' : 'border-fg/20'}`}>
                  <label className="flex items-center gap-2 font-semibold">
                    <input type="checkbox" checked={on} className="size-4 accent-[var(--color-magic-500)]"
                      onChange={(e) => setChosen((c) => ({ ...c, [doc.kind]: e.target.checked ? (doc.needs_month ? 'M-1' : '') : null }))} />
                    {doc.label}
                    <a href={doc.months[0]?.url ?? doc.url} target="_blank" rel="noreferrer" title={T.preview} className="ml-auto text-fg-3 hover:text-fg"><ExternalLink size={13} /></a>
                  </label>
                  {doc.needs_month && on && (
                    <select value={value ?? 'M-1'} onChange={(e) => setChosen((c) => ({ ...c, [doc.kind]: e.target.value }))} aria-label={T.month}
                      className="mt-1.5 w-full rounded-lg border-2 border-fg bg-card px-2 py-1 text-sm font-semibold">
                      <option value="M-1">{T.months['M-1']} · {T.loop}</option>
                      {doc.months.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                    </select>
                  )}
                  {doc.needs_month && <p className="mt-1 text-[0.7rem] font-semibold text-fg-3">{T.monthsOnline(doc.months.length, doc.months[0]?.label ?? '—')}</p>}
                </li>
              )
            })}
          </ul>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button variant="primary" onClick={() => onAdd(picks, data.fund || fund, data.part || part)} disabled={picks.length === 0} icon={<Plus size={16} />}>
              {T.addPicks(picks.length)}
            </Button>
            <span className="text-xs font-semibold text-fg-3">{T.addHint}</span>
          </div>
        </>
      )}
    </div>
  )
}
