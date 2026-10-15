/** Le questionnaire tel que le client l'a construit : chaque case réponse est colorée selon son état ; un clic la sélectionne. */
import { useEffect, useMemo, useRef, useState } from 'react'
import type { RfiPreview, RfiQuestion } from '../../../lib/types'
import { STATE_STYLE, type ReviewState } from './state'

export function SheetPreview({ preview, questions, states, selected, onSelect, zoom = 14 }: {
  preview: RfiPreview; questions: Record<string, RfiQuestion>; states: Record<string, ReviewState>
  selected: string | null; onSelect: (id: string) => void; zoom?: number
}) {
  const sheets = preview.sheets
  const selectedSheet = useMemo(() => {
    const loc = selected ? questions[selected]?.location : null
    return loc && loc.includes('!') ? loc.split('!')[0] : null
  }, [selected, questions])
  const [active, setActive] = useState(sheets[0]?.name ?? '')
  const scroller = useRef<HTMLDivElement>(null)

  useEffect(() => { if (selectedSheet && selectedSheet !== active) setActive(selectedSheet) }, [selectedSheet]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!selected) return
    const box = scroller.current
    const el = box?.querySelector<HTMLElement>(`[data-q="${selected}"]`)
    if (!box || !el) return
    const top = el.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop
    if (top < box.scrollTop + 40 || top > box.scrollTop + box.clientHeight - 40) {
      box.scrollTo({ top: Math.max(0, top - box.clientHeight / 3), behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
    }
  }, [selected, active])

  if (preview.kind === 'docx' || sheets.length === 0) {
    return (
      <ul className="flex flex-col gap-1.5" style={{ fontSize: `${zoom}px` }}>
        {preview.items.map((it) => (
          <li key={it.id}>
            <button data-q={it.id} onClick={() => onSelect(it.id)}
              className={`w-full rounded-lg border-2 px-3 py-2 text-left font-semibold ${selected === it.id ? 'border-fg shadow-[3px_3px_0_0_var(--color-fg)]' : 'border-fg/20'} ${STATE_STYLE[states[it.id] ?? 'none']}`}>
              <span className="text-[0.65rem] font-bold uppercase text-fg-3">{it.location}</span><br />{it.label}
            </button>
          </li>
        ))}
      </ul>
    )
  }
  const sheet = sheets.find((s) => s.name === active) ?? sheets[0]
  const hidden = new Set(sheet.hidden)
  return (
    <div className="flex h-full flex-col">
      {sheets.length > 1 && (
        <div role="tablist" className="mb-2 flex flex-wrap gap-1.5">
          {sheets.map((s) => (
            <button key={s.name} role="tab" aria-selected={s.name === sheet.name} onClick={() => setActive(s.name)}
              className={`rounded-full border-2 px-3 py-0.5 text-xs font-bold ${s.name === sheet.name ? 'border-fg bg-sun-400' : 'border-fg/25'}`}>
              {s.name} <span className="text-fg-3">{s.questions}</span>
            </button>
          ))}
        </div>
      )}
      <div ref={scroller} className="min-h-0 flex-1 overflow-auto rounded-xl border-2 border-fg bg-card">
        <table className="border-collapse leading-snug" style={{ fontSize: `${zoom}px` }}>
          <thead className="sticky top-0 z-10 bg-card-2">
            <tr>
              <th className="sticky left-0 z-20 w-8 border border-fg/15 bg-card-2" />
              {sheet.columns.map((c, i) => <th key={c} style={{ minWidth: `${sheet.widths[i] * zoom * 0.55}px` }} className="border border-fg/15 px-1 font-bold text-fg-3">{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {sheet.rows.map((row) => (
              <tr key={row.r}>
                <td className="sticky left-0 border border-fg/15 bg-card-2 px-1 text-right font-bold text-fg-3">{row.r}</td>
                {row.cells.map((cell) => {
                  if (hidden.has(cell.ref)) return null
                  const span = sheet.merged[cell.ref]
                  const q = cell.q ? questions[cell.q] : undefined
                  const state = cell.q ? states[cell.q] ?? 'none' : null
                  const proposed = q && q.state !== 'answered' && q.answer ? q.answer : null  // la consigne du client est remplacée par la proposition
                  const shown = proposed ?? cell.v
                  return (
                    <td key={cell.ref} colSpan={span?.[0]} rowSpan={span?.[1]}
                      style={{ maxWidth: `${zoom * 32}px` }} className={`border border-fg/15 px-2 py-1.5 align-top ${state ? `${STATE_STYLE[state]} cursor-pointer` : ''} ${cell.q && cell.q === selected ? 'outline outline-[3px] -outline-offset-2 outline-fg' : ''}`}>
                      {cell.q ? (
                        <button data-q={cell.q} onClick={() => onSelect(cell.q!)} className={`block w-full text-left ${proposed ? 'font-bold italic' : ''}`}>
                          {shown || '·'}
                        </button>
                      ) : <span className="line-clamp-3 whitespace-pre-line">{cell.v}</span>}
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
