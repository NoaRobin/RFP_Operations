/**
 * Le détail d'une case : la question, la part, la réponse proposée et sa preuve, puis toutes les réponses possibles
 * (carrousel du compléteur : Fabric, DIC / prospectus, anciens RFI, Qvidian…), « Choisir », ou une réponse saisie.
 */
import { useEffect, useState } from 'react'
import { Check, CircleSlash, PenLine, RotateCcw, X } from 'lucide-react'
import { texts } from '../../../content/texts'
import type { RfiQuestion } from '../../../lib/types'
import { SourceCarousel } from '../../rfi/review/SourceCarousel'
import { STATE_STYLE, type Override, type ReviewState } from '../../rfi/review/state'
import { Button } from '../../ui/Button'
import type { GridRow } from './model'

const G = texts.grid
const norm = (v: string) => v.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim()

export function CellPanel({ q, row, state, override, onOverride, onAccept, onClose }: {
  q: RfiQuestion | null; row: GridRow | null; state: ReviewState | null; override: Override | undefined
  onOverride: (v: Override | undefined) => void; onAccept: () => void; onClose: () => void
}) {
  const [draft, setDraft] = useState('')
  const [writing, setWriting] = useState(false)
  useEffect(() => { setDraft(''); setWriting(false) }, [q?.id])
  if (!q || !state) {
    return <aside className="rounded-[var(--radius-card)] border-2 border-dashed border-fg/30 p-5 text-sm font-semibold text-fg-2">{G.cell.empty}</aside>
  }
  const choose = (value: string, adapt: boolean) => {
    const option = q.options.length ? q.options.find((o) => norm(o) === norm(value)) : value
    if (adapt || option === undefined) { setDraft(option ?? value); setWriting(true); return }
    onOverride({ text: option })
  }
  const shown = state === 'existing' ? q.existing : (override && typeof override === 'object' ? override.text : q.answer)
  return (
    <aside className="flex flex-col gap-4 rounded-[var(--radius-card)] border-[2.5px] border-fg bg-card p-4 shadow-[4px_4px_0_0_var(--color-fg)] xl:sticky xl:top-24 xl:max-h-[calc(100vh-7rem)] xl:overflow-y-auto" aria-label={q.question} data-lenis-prevent>
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="font-mono text-xs font-bold text-fg-2">{row?.isin} · {q.location}</p>
          <h2 className="mt-1 text-lg leading-snug">{q.question}</h2>
          {row?.share?.known && <p className="text-xs font-semibold text-fg-3">{row.share.fund}{row.share.share_name ? ` · ${row.share.share_name}` : ''}</p>}
        </div>
        <button onClick={onClose} aria-label="Fermer" className="grid size-8 place-items-center rounded-full border-2 border-fg/30 hover:border-fg"><X size={15} /></button>
      </div>

      <div className="rounded-2xl border-2 border-fg bg-card-2 p-3">
        <span className={`inline-flex rounded-full border-2 border-fg px-2 py-0.5 text-xs font-bold ${STATE_STYLE[state]}`}>{G.states[state]}</span>
        <p className={`mt-2 whitespace-pre-wrap break-words ${shown ? 'font-display text-lg font-semibold' : 'text-sm italic text-fg-2'}`}>{shown ?? G.cell.nothing}</p>
        <dl className="mt-2 grid gap-1 text-xs">
          {q.concept_label && <div><dt className="inline font-bold text-fg-2">{G.cell.source} : </dt><dd className="inline">{q.source} · {q.concept_label}</dd></div>}
          {q.data_date && <div><dt className="inline font-bold text-fg-2">{G.cell.dataDate} : </dt><dd className="inline">{q.data_date}</dd></div>}
          {q.evidence && <div><dt className="inline font-bold text-fg-2">{G.cell.evidence} : </dt><dd className="inline break-words">{q.evidence}</dd></div>}
          {q.understanding.length > 0 && <div><dt className="inline font-bold text-fg-2">{G.cell.understanding} : </dt><dd className="inline">{q.understanding.join(' · ')}</dd></div>}
          {q.state === 'answered' && state !== 'existing' && <div><dt className="inline font-bold text-fg-2">{G.cell.existing} : </dt><dd className="inline">{q.existing}</dd></div>}
        </dl>
        {q.issues.length > 0 && (
          <ul className="mt-2 list-disc pl-5 text-xs font-semibold text-danger" aria-label={G.cell.issues}>{q.issues.map((i) => <li key={i}>{i}</li>)}</ul>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          {state === 'review' && <Button size="sm" variant="primary" icon={<Check size={14} />} onClick={onAccept}>{G.cell.accept}</Button>}
          {state !== 'skipped' && <Button size="sm" icon={<CircleSlash size={14} />} onClick={() => onOverride(null)}>{G.cell.skip}</Button>}
          {override !== undefined && <Button size="sm" variant="ghost" icon={<RotateCcw size={14} />} onClick={() => onOverride(undefined)}>{G.cell.reset}</Button>}
          {!writing && <Button size="sm" variant="ghost" icon={<PenLine size={14} />} onClick={() => { setDraft(shown ?? ''); setWriting(true) }}>{G.cell.write}</Button>}
        </div>
        {writing && (
          <form className="mt-3 flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); if (draft.trim()) onOverride({ text: draft.trim() }); setWriting(false) }}>
            <label className="sr-only" htmlFor={`write-${q.id}`}>{G.cell.writeLabel}</label>
            {q.options.length ? (
              <select id={`write-${q.id}`} value={draft} onChange={(e) => setDraft(e.target.value)} className="rounded-xl border-2 border-fg bg-field px-3 py-2 text-sm">
                <option value="">—</option>
                {q.options.map((o) => <option key={o}>{o}</option>)}
              </select>
            ) : (
              <textarea id={`write-${q.id}`} autoFocus rows={3} value={draft} onChange={(e) => setDraft(e.target.value)}
                className="rounded-xl border-2 border-fg bg-field px-3 py-2 text-sm" />
            )}
            <div><Button size="sm" variant="primary" type="submit" disabled={!draft.trim()}>{G.cell.use}</Button></div>
          </form>
        )}
      </div>

      {(q.choices?.length ?? 0) > 0 && <SourceCarousel q={q} override={override} onChoose={choose} onEdit={(v) => { setDraft(v); setWriting(true) }} />}
      <p className="text-[0.7rem] font-semibold text-fg-3">{G.cell.keys}</p>
    </aside>
  )
}
