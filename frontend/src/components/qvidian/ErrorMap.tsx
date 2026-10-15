/**
 * Carte des erreurs : dossiers de la bibliothèque (lignes) × catégories de défaut (colonnes). Chaque case donne le
 * nombre de contenus touchés ; la couleur fonce avec la proportion du dossier concernée. Un clic filtre la liste.
 */
import { texts } from '../../content/texts'
import type { QvidianAudit } from '../../lib/types'

const Q = texts.qvidian
const SEVERITY_BG: Record<string, string> = { haute: 'bg-bubble-400', moyenne: 'bg-sun-400', basse: 'bg-mint-400' }

export interface MapFilter { group: string | null; category: string | null }

export function ErrorMap({ audit, filter, onFilter }: { audit: QvidianAudit; filter: MapFilter; onFilter: (f: MapFilter) => void }) {
  const cats = audit.categories.filter((c) => c.count > 0 || c.key === 'ia')
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        {audit.categories.map((c) => (
          <button key={c.key} onClick={() => onFilter({ group: null, category: filter.category === c.key && !filter.group ? null : c.key })}
            aria-pressed={filter.category === c.key && !filter.group} disabled={c.count === 0}
            className={`flex items-center gap-2 rounded-2xl border-[2.5px] border-fg px-3 py-1.5 text-left transition-transform enabled:hover:-translate-y-0.5 disabled:opacity-40 ${filter.category === c.key && !filter.group ? 'bg-fg text-canvas' : 'bg-card'}`}>
            <span className={`size-3 rounded-full border border-fg ${SEVERITY_BG[c.severity] ?? 'bg-card-3'}`} aria-hidden="true" />
            <span className="font-display text-xl font-semibold tabular-nums">{c.count}</span>
            <span className="text-sm font-bold">{c.label}</span>
          </button>
        ))}
      </div>

      <div className="overflow-x-auto rounded-2xl border-2 border-fg bg-card">
        <table className="w-full min-w-[44rem] border-collapse text-sm">
          <caption className="sr-only">{Q.mapTitle}</caption>
          <thead>
            <tr className="bg-card-2">
              <th scope="col" className="sticky left-0 bg-card-2 px-3 py-2 text-left font-bold">Dossier</th>
              {cats.map((c) => <th key={c.key} scope="col" className="px-2 py-2 text-center text-xs font-bold">{c.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {audit.groups.map((g) => (
              <tr key={g.group} className="border-t border-fg/15">
                <th scope="row" className="sticky left-0 bg-card px-3 py-1.5 text-left font-semibold">
                  <button onClick={() => onFilter({ group: filter.group === g.group && !filter.category ? null : g.group, category: null })}
                    className={`text-left hover:underline ${filter.group === g.group && !filter.category ? 'underline decoration-2' : ''}`}>
                    {g.group}
                  </button>
                  <span className="block text-[0.7rem] font-semibold text-fg-3">{g.total} {Q.total}{g.with_issues === 0 ? ` · ${Q.clean}` : ''}</span>
                </th>
                {cats.map((c) => {
                  const n = g.counts[c.key] ?? 0
                  const ratio = g.total ? n / g.total : 0
                  const active = filter.group === g.group && filter.category === c.key
                  const shade = n === 0 ? 'bg-transparent text-fg-3' : ratio >= 0.5 ? 'bg-bubble-400' : ratio >= 0.25 ? 'bg-sun-400' : 'bg-sun-400/45'
                  return (
                    <td key={c.key} className="p-1 text-center">
                      <button disabled={n === 0} onClick={() => onFilter(active ? { group: null, category: null } : { group: g.group, category: c.key })}
                        aria-label={`${g.group} · ${c.label} : ${n}`} aria-pressed={active}
                        className={`h-9 w-full min-w-[3rem] rounded-lg border-2 font-bold tabular-nums transition-transform enabled:hover:scale-105 ${active ? 'border-fg ring-2 ring-magic-400' : n ? 'border-fg/60' : 'border-fg/10'} ${shade}`}>
                        {n || '·'}
                      </button>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
