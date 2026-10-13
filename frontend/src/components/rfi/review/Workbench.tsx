/**
 * Atelier de revue en trois zones : le document (ou la liste), la question en grand, les preuves.
 * Clavier : J / K naviguer, A valider, E modifier, S autre source, X ignorer (jamais quand on écrit dans un champ).
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { CheckCheck, Keyboard } from 'lucide-react'
import { texts } from '../../../content/texts'
import type { RfiAnalysis, RfiFact, RfiPreview } from '../../../lib/types'
import { EvidencePanel } from './EvidencePanel'
import { ProgressRing } from './ProgressRing'
import { QuestionCard, type QuestionCardHandle } from './QuestionCard'
import { QuestionList } from './QuestionList'
import { SheetPreview } from './SheetPreview'
import { reviewState, type Override, type ReviewState } from './state'

type Filter = 'todo' | 'review' | 'auto' | 'none' | 'all'

export function Workbench({ analysis, preview, facts, overrides, accepted, onAccept, onAcceptMany, onOverride }: {
  analysis: RfiAnalysis; preview: RfiPreview | null; facts: RfiFact[]; overrides: Record<string, Override>; accepted: Set<string>
  onAccept: (id: string, on: boolean) => void; onAcceptMany: (ids: string[]) => void; onOverride: (id: string, v: Override | undefined) => void
}) {
  const [tab, setTab] = useState<'document' | 'list'>(preview && preview.kind === 'xlsx' && preview.sheets.length ? 'document' : 'list')
  const [filter, setFilter] = useState<Filter>('todo')
  const [selected, setSelected] = useState<string | null>(null)
  const card = useRef<QuestionCardHandle>(null)

  const byId = useMemo(() => Object.fromEntries(analysis.questions.map((q) => [q.id, q])), [analysis])
  const states = useMemo(() => Object.fromEntries(analysis.questions.map((q) => [q.id, reviewState(q, accepted, overrides[q.id])])) as Record<string, ReviewState>,
    [analysis, accepted, overrides])
  const counts = useMemo(() => {
    const c: Record<ReviewState, number> = { auto: 0, accepted: 0, review: 0, none: 0, skipped: 0, existing: 0 }
    for (const s of Object.values(states)) c[s] += 1
    return c
  }, [states])
  const visible = useMemo(() => analysis.questions.filter((q) => {
    const s = states[q.id]
    return filter === 'all' ? true : filter === 'todo' ? s === 'review' || s === 'none' : filter === 'review' ? s === 'review'
      : filter === 'auto' ? s === 'auto' || s === 'accepted' : s === 'none'
  }), [analysis, states, filter])
  const order = tab === 'list' ? visible : analysis.questions
  const index = selected ? order.findIndex((q) => q.id === selected) : -1

  useEffect(() => { if (!selected || !byId[selected]) setSelected(visible[0]?.id ?? analysis.questions[0]?.id ?? null) }, [analysis]) // eslint-disable-line react-hooks/exhaustive-deps

  const move = (step: number) => {
    if (order.length === 0) return
    const next = order[(Math.max(index, 0) + step + order.length) % order.length]
    setSelected(next.id)
  }
  const acceptAndNext = () => {
    if (selected && states[selected] === 'review') onAccept(selected, true)
    move(1)
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (e.metaKey || e.ctrlKey || e.altKey || ['INPUT', 'SELECT', 'TEXTAREA'].includes(t.tagName) || t.isContentEditable) return
      const k = e.key.toLowerCase()
      if (k === 'j' || e.key === 'ArrowDown') { e.preventDefault(); move(1) }
      else if (k === 'k' || e.key === 'ArrowUp') { e.preventDefault(); move(-1) }
      else if (k === 'a') { e.preventDefault(); acceptAndNext() }
      else if (k === 'e') { e.preventDefault(); card.current?.edit() }
      else if (k === 's') { e.preventDefault(); card.current?.source() }
      else if (k === 'x' && selected) { e.preventDefault(); onOverride(selected, null); move(1) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const docConfirmed = analysis.questions.filter((q) => states[q.id] === 'review' && (q.sources ?? []).some((s) => (s.kind === 'kid' || s.kind === 'prospectus') && s.check === 'match')).map((q) => q.id)
  const firm = analysis.questions.filter((q) => states[q.id] === 'review' && q.precedent?.kind === 'precedent_constant').map((q) => q.id)
  const visibleReview = visible.filter((q) => states[q.id] === 'review').map((q) => q.id)
  const q = selected ? byId[selected] : null

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border-2 border-fg bg-card-2 p-4">
        <ProgressRing counts={counts} />
        <div className="flex flex-wrap gap-2">
          {docConfirmed.length > 0 && <BulkButton label={texts.review.bulkDocs(docConfirmed.length)} onClick={() => onAcceptMany(docConfirmed)} />}
          {firm.length > 0 && <BulkButton label={texts.review.bulkFirm(firm.length)} onClick={() => onAcceptMany(firm)} />}
          {visibleReview.length > 0 && <BulkButton label={texts.review.bulkVisible(visibleReview.length)} onClick={() => onAcceptMany(visibleReview)} />}
        </div>
        <p className="flex w-full items-center gap-1.5 text-xs font-semibold text-fg-3"><Keyboard size={14} aria-hidden="true" />{texts.review.shortcuts}</p>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)_minmax(0,0.85fr)]">
        <section className="flex max-h-[78vh] min-h-[24rem] flex-col rounded-[var(--radius-card)] border-2 border-fg bg-card p-3">
          <div className="mb-2 flex flex-wrap items-center gap-1.5">
            {(['document', 'list'] as const).map((t) => (
              <button key={t} onClick={() => setTab(t)} aria-pressed={tab === t} disabled={t === 'document' && !preview}
                className={`rounded-full border-2 px-3 py-0.5 text-sm font-bold ${tab === t ? 'border-fg bg-magic-500 text-white' : 'border-fg/30'}`}>{texts.review.tabs[t]}</button>
            ))}
            {tab === 'list' && (
              <span className="ml-auto flex flex-wrap gap-1">
                {(['todo', 'review', 'none', 'auto', 'all'] as Filter[]).map((f) => (
                  <button key={f} onClick={() => setFilter(f)} aria-pressed={filter === f}
                    className={`rounded-full border px-2 py-px text-[0.7rem] font-bold ${filter === f ? 'border-fg bg-sun-400' : 'border-fg/25'}`}>{texts.review.filters[f]}</button>
                ))}
              </span>
            )}
          </div>
          <div className="min-h-0 flex-1 overflow-auto">
            {tab === 'document' && preview ? (
              <SheetPreview preview={preview} questions={byId} states={states} selected={selected} onSelect={setSelected} />
            ) : (
              <QuestionList questions={visible} states={states} selected={selected} onSelect={setSelected} />
            )}
          </div>
        </section>

        <section className="min-w-0">
          {q ? (
            <QuestionCard ref={card} q={q} state={states[q.id]} override={overrides[q.id]} facts={facts}
              position={`${index + 1} / ${order.length}`} onPrev={() => move(-1)} onNext={() => move(1)}
              onAccept={acceptAndNext} onOverride={(v) => onOverride(q.id, v)} />
          ) : <p className="font-semibold text-fg-2">{texts.review.pick}</p>}
        </section>

        <aside className="max-h-[78vh] min-w-0 overflow-auto rounded-[var(--radius-card)] border-2 border-fg/25 bg-card-2 p-3">
          <EvidencePanel q={q} onUse={(value) => q && onOverride(q.id, { text: value })} />
        </aside>
      </div>
    </div>
  )
}

function BulkButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button onClick={onClick} className="inline-flex items-center gap-1.5 rounded-full border-2 border-fg bg-card px-3.5 py-1.5 text-sm font-bold shadow-[2px_2px_0_0_var(--color-fg)] transition-transform hover:-translate-y-0.5">
      <CheckCheck size={15} aria-hidden="true" />{label}
    </button>
  )
}
