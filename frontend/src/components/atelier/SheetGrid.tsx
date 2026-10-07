/**
 * Grille façon tableur : en-têtes dorés, colonne clé arcane, cellules cibles qui s'illuminent,
 * colonnes déposables (glisser-déposer) et sélectionnables au clavier.
 * En aperçu, les nouvelles valeurs « tombent » dans leurs cellules.
 */
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { texts } from '../../content/texts'
import type { Change, Extraction, Mapping, Preview, SheetAnalysis } from '../../lib/types'
import { gsap } from '../../motion/gsap'
import { d, dist } from '../../motion/tokens'

export const DRAG_TYPE = 'application/x-merlin-extraction'

const STATUS_STYLE: Record<string, string> = {
  fill: 'text-gold-200 bg-gold-400/12',
  overwrite: 'text-violet-300 bg-violet-500/15',
  conflict: 'text-warning bg-warning/10 underline decoration-dotted',
  unchanged: 'text-success/90',
  not_found: 'text-danger bg-danger/10',
  protected: 'text-haze',
}

interface Props {
  sheet: SheetAnalysis
  headerRow: number
  keyColumn: string
  mappings: Mapping[]
  extractions: Record<string, Extraction>
  selectedColumn: string | null
  onSelectColumn: (col: string | null) => void
  onDrop: (column: string, extractionId: string) => void
  onRemove: (column: string) => void
  preview: Preview | null
  showAfter: boolean
}

export function SheetGrid({ sheet, headerRow, keyColumn, mappings, extractions, selectedColumn, onSelectColumn, onDrop, onRemove, preview, showAfter }: Props) {
  const wrapper = useRef<HTMLDivElement>(null)
  const [dragOver, setDragOver] = useState<string | null>(null)
  const targets = useMemo(() => new Set(sheet.targets), [sheet.targets])
  const mapped = useMemo(() => Object.fromEntries(mappings.map((m) => [m.column, m.extraction])), [mappings])
  const changes = useMemo(() => {
    const map = new Map<string, Change>()
    preview?.changes.forEach((c) => map.set(c.cell, c))
    return map
  }, [preview])

  // Les valeurs tombent dans les cellules
  useLayoutEffect(() => {
    if (!preview || !showAfter || !wrapper.current) return
    const drops = wrapper.current.querySelectorAll('[data-drop]')
    gsap.fromTo(drops, { y: -dist('fall'), opacity: 0, scale: 1.3 }, {
      y: 0, opacity: 1, scale: 1, duration: d('slow'), ease: 'bounce.out',
      stagger: { each: Math.min(0.02, 1.2 / Math.max(drops.length, 1)), from: 'start' },
    })
  }, [preview, showAfter])

  const dropHandlers = (column: string) => ({
    onDragOver: (e: React.DragEvent) => {
      if (!e.dataTransfer.types.includes(DRAG_TYPE) || column === keyColumn) return
      e.preventDefault()
      e.dataTransfer.dropEffect = 'copy'
      if (dragOver !== column) setDragOver(column)
    },
    onDragLeave: () => setDragOver((c) => (c === column ? null : c)),
    onDrop: (e: React.DragEvent) => {
      const id = e.dataTransfer.getData(DRAG_TYPE)
      setDragOver(null)
      if (id && column !== keyColumn) {
        e.preventDefault()
        onDrop(column, id)
      }
    },
  })

  const { rows, cols } = sheet.grid
  return (
    <div className="glass overflow-hidden rounded-[var(--radius-card)]">
      <div ref={wrapper} className="max-h-[36rem] overflow-auto" data-lenis-prevent>
        <table className="border-separate border-spacing-0 text-[0.8rem]" aria-label={texts.atelier.gridLabel(sheet.name)}>
          <thead className="sticky top-0 z-20">
            <tr>
              <th scope="col" className="sticky left-0 z-30 w-12 min-w-12 border-b border-r hairline bg-ink-2" aria-label="Lignes" />
              {cols.map((col) => {
                const extraction = mapped[col] ? extractions[mapped[col]] : undefined
                const isKey = col === keyColumn
                const selected = selectedColumn === col
                return (
                  <th key={col} scope="col" {...dropHandlers(col)}
                    className={`min-w-36 border-b border-r hairline bg-ink-2 p-1 align-top transition-colors ${dragOver === col ? '!bg-arcane-400/25' : ''}`}>
                    <button
                      type="button"
                      onClick={() => onSelectColumn(selected ? null : col)}
                      aria-pressed={selected}
                      disabled={isKey}
                      aria-label={`Colonne ${col}${isKey ? ' (clé)' : ''}${extraction ? ` : ${extraction.label}` : ''}`}
                      className={`w-full rounded-md px-2 py-1 font-mono text-xs font-bold transition-all ${
                        selected ? 'bg-gold-400 text-abyss shadow-[var(--shadow-glow-gold)]' : isKey ? 'text-arcane-300' : 'text-mist hover:bg-white/10'}`}
                    >
                      {col}{isKey ? ' · clé' : ''}
                    </button>
                    {extraction && (
                      <span className="mt-1 flex items-center gap-1 rounded-md border border-gold-400/40 bg-gold-400/10 px-1.5 py-0.5 text-left text-[0.7rem] font-medium text-gold-200">
                        <span className="truncate">{extraction.label}</span>
                        <button type="button" onClick={() => onRemove(col)} aria-label={texts.atelier.removeMapping(col)} className="ml-auto shrink-0 text-gold-300 hover:text-parchment">
                          <X size={12} />
                        </button>
                      </span>
                    )}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, r) => {
              const rowNumber = r + 1
              const isHeader = rowNumber === headerRow
              return (
                <tr key={rowNumber}>
                  <th scope="row" className={`sticky left-0 z-10 border-b border-r hairline bg-ink-2 px-2 text-right font-mono text-[0.7rem] ${isHeader ? 'text-gold-300' : 'text-haze'}`}>
                    {rowNumber}
                  </th>
                  {row.map((cell, c) => {
                    const col = cols[c]
                    const ref = `${col}${rowNumber}`
                    const change = changes.get(ref)
                    const isTarget = targets.has(ref)
                    const isMappedTarget = isTarget && !!mapped[col]
                    const showChange = change && showAfter && change.status !== 'protected'
                    let cls = 'text-mist'
                    if (isHeader) cls = 'bg-gold-400/10 font-semibold text-gold-200'
                    else if (col === keyColumn && rowNumber > headerRow) cls = 'bg-arcane-400/[0.07] font-mono text-arcane-300'
                    else if (cell.f) cls = 'text-haze italic'
                    return (
                      <td key={col} {...dropHandlers(col)}
                        className={`relative h-8 max-w-64 border-b border-r hairline px-2 ${cell.n ? 'text-right tabular-nums' : ''} ${cls} ${
                          selectedColumn === col ? 'bg-gold-400/[0.06]' : ''} ${dragOver === col ? 'bg-arcane-400/10' : ''}`}>
                        {isTarget && !showChange && (
                          <span aria-hidden="true" className={`pointer-events-none absolute inset-0.5 rounded-sm ${isMappedTarget ? 'animate-pulse-glow' : 'shadow-[inset_0_0_0_1px_rgb(94_234_212/0.35)]'}`} />
                        )}
                        {showChange ? (
                          <span data-drop={change.status === 'fill' || change.status === 'overwrite' ? '' : undefined}
                            title={change.before ? `${texts.atelier.before} : ${change.before}` : undefined}
                            className={`block truncate rounded px-1 ${STATUS_STYLE[change.status]}`}>
                            {change.status === 'not_found' ? '∅' : change.status === 'conflict' ? cell.v : change.after}
                          </span>
                        ) : (
                          <span className="block truncate">{cell.v}</span>
                        )}
                      </td>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {(sheet.grid.truncated_rows || sheet.grid.truncated_cols) && (
        <p className="border-t hairline px-4 py-2 text-xs text-haze">{texts.atelier.truncated}</p>
      )}
    </div>
  )
}
