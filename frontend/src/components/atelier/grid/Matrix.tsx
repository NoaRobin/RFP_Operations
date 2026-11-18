/**
 * La grille : ISIN en lignes (colonne collante à gauche), questions en colonnes (en-tête collant en haut).
 * Chaque case montre la réponse proposée et son état (couleur + pastille, jamais la couleur seule).
 * Clavier : flèches pour se déplacer, A accepter, Suppr ne pas remplir, Échap pour quitter la case.
 */
import { useEffect, useRef, useState } from 'react'
import { Check, ChevronDown, CircleSlash, RotateCcw, Shuffle } from 'lucide-react'
import { texts } from '../../../content/texts'
import type { RfiFact } from '../../../lib/types'
import { STATE_DOT } from '../../rfi/review/state'
import { filled, type Grid, type GridColumn, type States } from './model'

const G = texts.grid
const TONE: Record<string, string> = {
  auto: 'bg-mint-400/20', accepted: 'bg-magic-400/20', review: 'bg-sun-400/40', none: 'bg-bubble-400/15',
  skipped: 'bg-card-2 text-fg-3', existing: 'bg-card-3/70',
}

function Bar({ value }: { value: number }) {
  return (
    <span className="mt-1 block h-1.5 w-full overflow-hidden rounded-full bg-fg/10" aria-hidden="true">
      <span className="block h-full rounded-full bg-mint-500" style={{ width: `${Math.round(value * 100)}%` }} />
    </span>
  )
}

function ColumnMenu({ col, facts, onAction }: {
  col: GridColumn; facts: RfiFact[]
  onAction: (action: 'accept' | 'skip' | 'reset' | { concept: string }) => void
}) {
  const [open, setOpen] = useState(false)
  const [picking, setPicking] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) { setOpen(false); setPicking(false) } }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') { setOpen(false); setPicking(false) } }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc) }
  }, [open])
  const act = (a: Parameters<typeof onAction>[0]) => { onAction(a); setOpen(false); setPicking(false) }
  return (
    <div ref={box} className="relative">
      <button onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open} aria-label={G.column.menu(col.question)}
        className="grid size-6 place-items-center rounded-md hover:bg-fg/10"><ChevronDown size={14} /></button>
      {open && (
        <div role="menu" className="absolute right-0 top-7 z-30 w-72 rounded-xl border-2 border-fg bg-card p-1.5 text-left font-sans text-sm font-semibold normal-case shadow-[3px_3px_0_0_var(--color-fg)]">
          {!picking ? (
            <>
              <button role="menuitem" onClick={() => act('accept')} className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 hover:bg-card-2"><Check size={14} />{G.column.accept}</button>
              <button role="menuitem" onClick={() => setPicking(true)} className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 hover:bg-card-2"><Shuffle size={14} />{G.column.concept}</button>
              <button role="menuitem" onClick={() => act('skip')} className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 hover:bg-card-2"><CircleSlash size={14} />{G.column.skip}</button>
              <button role="menuitem" onClick={() => act('reset')} className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 hover:bg-card-2"><RotateCcw size={14} />{G.column.reset}</button>
            </>
          ) : (
            <label className="block p-1.5">
              <span className="text-xs text-fg-2">{G.column.pick}</span>
              <select autoFocus defaultValue={col.concept ?? ''} onChange={(e) => e.target.value && act({ concept: e.target.value })}
                className="mt-1 w-full rounded-lg border-2 border-fg bg-field px-2 py-1.5 text-sm">
                <option value="" disabled>—</option>
                {facts.filter((f) => f.healthy).map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
              </select>
            </label>
          )}
        </div>
      )}
    </div>
  )
}

export function Matrix({ grid, states, rows, selected, onSelect, onKey, onColumn, facts }: {
  grid: Grid; states: States; rows: Grid['rows']; selected: string | null
  onSelect: (id: string | null) => void; onKey: (key: 'accept' | 'skip') => void
  onColumn: (col: GridColumn, action: 'accept' | 'skip' | 'reset' | { concept: string }) => void; facts: RfiFact[]
}) {
  const wrap = useRef<HTMLDivElement>(null)
  const pos = (() => {
    for (let r = 0; r < rows.length; r++) {
      for (let c = 0; c < grid.columns.length; c++) if (rows[r].cells[grid.columns[c].key]?.id === selected) return [r, c]
    }
    return null
  })()

  useEffect(() => {
    if (!selected) return
    wrap.current?.querySelector<HTMLElement>(`[data-cell="${selected}"]`)?.focus({ preventScroll: false })
  }, [selected])

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!pos) return
    const [r, c] = pos
    const go = (nr: number, nc: number) => {
      const row = rows[Math.max(0, Math.min(rows.length - 1, nr))]
      const col = grid.columns[Math.max(0, Math.min(grid.columns.length - 1, nc))]
      const q = row?.cells[col.key]
      if (q) { e.preventDefault(); onSelect(q.id) }
    }
    if (e.key === 'ArrowDown') go(r + 1, c)
    else if (e.key === 'ArrowUp') go(r - 1, c)
    else if (e.key === 'ArrowRight') go(r, c + 1)
    else if (e.key === 'ArrowLeft') go(r, c - 1)
    else if (e.key.toLowerCase() === 'a') { e.preventDefault(); onKey('accept') }
    else if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); onKey('skip') }
    else if (e.key === 'Escape') onSelect(null)
  }

  return (
    <div ref={wrap} className="max-h-[calc(100vh-14rem)] min-h-[24rem] overflow-auto rounded-[var(--radius-card)] border-[2.5px] border-fg bg-card" data-lenis-prevent onKeyDown={onKeyDown}>
      <table className="border-separate border-spacing-0 text-sm" role="grid" aria-label={grid.sheet}>
        <thead>
          <tr>
            <th scope="col" className="sticky left-0 top-0 z-20 border-b-2 border-r-2 border-fg bg-card-2 px-3 py-2 text-left align-bottom font-display text-xs uppercase tracking-wide text-fg-2">
              {G.isins} · {rows.length}
            </th>
            {grid.columns.map((col) => (
              <th key={col.key} scope="col" className="sticky top-0 z-10 w-56 min-w-[13rem] max-w-[16rem] border-b-2 border-r border-fg/15 bg-card-2 px-3 py-2 text-left align-bottom">
                <div className="flex items-start gap-1">
                  <span className="line-clamp-2 flex-1 font-display text-[0.82rem] font-semibold leading-tight" title={col.question}>{col.question}</span>
                  <ColumnMenu col={col} facts={facts} onAction={(a) => onColumn(col, a)} />
                </div>
                <span className="mt-0.5 block truncate text-[0.7rem] font-semibold text-fg-3" title={col.conceptLabel ?? ''}>{col.conceptLabel ?? '—'}</span>
                <Bar value={filled(col.ids, states)} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const ids = Object.values(row.cells).map((q) => q.id)
            return (
              <tr key={row.isin}>
                <th scope="row" className="sticky left-0 z-10 border-b border-r-2 border-fg/15 border-r-fg bg-card px-3 py-2 text-left align-top">
                  <div className="w-44">
                    <span className="block font-mono text-[0.8rem] font-bold">{row.isin}</span>
                    <span className="block truncate text-xs font-semibold text-fg-2" title={row.share?.known ? `${row.share.fund ?? ''} · ${row.share.share_name ?? ''}` : G.unknown}>
                      {row.share?.known ? (row.share.share_name ?? row.share.fund) : <span className="text-danger">{G.unknown}</span>}
                    </span>
                    <Bar value={filled(ids, states)} />
                  </div>
                </th>
                {grid.columns.map((col) => {
                  const q = row.cells[col.key]
                  if (!q) return <td key={col.key} className="border-b border-r border-fg/10 bg-card-2/50" />
                  const s = states[q.id]
                  const active = q.id === selected
                  return (
                    <td key={col.key} className="border-b border-r border-fg/10 p-0 align-top">
                      <button data-cell={q.id} onClick={() => onSelect(active ? null : q.id)} aria-pressed={active}
                        aria-label={`${row.isin} · ${col.question} : ${q.answer ?? G.states[s]} (${G.states[s]})`}
                        className={`flex h-full min-h-[3.25rem] w-full items-start gap-2 px-3 py-2 text-left outline-none transition-colors ${TONE[s]} ${active ? 'ring-[3px] ring-inset ring-fg' : 'hover:brightness-95 focus-visible:ring-[3px] focus-visible:ring-inset focus-visible:ring-magic-500'}`}>
                        <span className={`mt-1.5 size-2 shrink-0 rounded-full ${STATE_DOT[s]}`} aria-hidden="true" />
                        <span className={`line-clamp-2 min-w-0 break-words ${s === 'skipped' ? 'line-through' : ''} ${q.answer == null && s !== 'existing' ? 'italic text-fg-3' : 'font-semibold'}`}>
                          {s === 'existing' ? q.existing : q.answer ?? '—'}
                        </span>
                      </button>
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
