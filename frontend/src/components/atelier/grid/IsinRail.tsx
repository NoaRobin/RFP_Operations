/** Le rail des ISIN : toutes les parts de la grille, fonds et part Product Info, avancement ; filtre et accès direct. */
import { Search } from 'lucide-react'
import { texts } from '../../../content/texts'
import { filled, type Grid, type States } from './model'

const G = texts.grid

export function IsinRail({ grid, states, query, onQuery, focus, onFocus }: {
  grid: Grid; states: States; query: string; onQuery: (q: string) => void; focus: string | null; onFocus: (isin: string | null) => void
}) {
  const q = query.trim().toLowerCase()
  const rows = grid.rows.filter((r) => !q || `${r.isin} ${r.share?.fund ?? ''} ${r.share?.share_name ?? ''}`.toLowerCase().includes(q))
  return (
    <aside className="flex flex-col gap-3 rounded-[var(--radius-card)] border-[2.5px] border-fg bg-card p-3 lg:sticky lg:top-24 lg:max-h-[calc(100vh-7rem)]" aria-label={G.isins} data-lenis-prevent>
      <label className="relative block">
        <span className="sr-only">{G.isinFilter}</span>
        <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-3" aria-hidden="true" />
        <input value={query} onChange={(e) => onQuery(e.target.value)} placeholder={G.isinFilter} type="search"
          className="h-10 w-full rounded-xl border-2 border-fg bg-field pl-9 pr-3 text-sm font-semibold placeholder:font-normal placeholder:text-fg-3 focus:outline-none focus:ring-2 focus:ring-magic-500" />
      </label>
      <ul className="-mx-1 flex flex-col gap-1 overflow-y-auto px-1">
        {rows.map((r) => {
          const ids = Object.values(r.cells).map((x) => x.id)
          const rate = filled(ids, states)
          const active = focus === r.isin
          return (
            <li key={r.isin}>
              <button onClick={() => onFocus(active ? null : r.isin)} aria-pressed={active}
                className={`w-full rounded-xl border-2 px-3 py-2 text-left transition-colors ${active ? 'border-fg bg-sun-400' : 'border-transparent hover:border-fg/30 hover:bg-card-2'}`}>
                <span className="flex items-baseline gap-2">
                  <span className="font-mono text-[0.8rem] font-bold">{r.isin}</span>
                  <span className="ml-auto font-mono text-[0.7rem] font-bold text-fg-2">{Math.round(rate * 100)} %</span>
                </span>
                <span className="block truncate text-xs font-semibold text-fg-2">
                  {r.share?.known ? (r.share.share_name ?? r.share.fund) : <span className="text-danger">{G.unknown}</span>}
                </span>
                {r.share?.known && r.share.fund && <span className="block truncate text-[0.7rem] text-fg-3">{r.share.fund}</span>}
              </button>
            </li>
          )
        })}
      </ul>
    </aside>
  )
}
