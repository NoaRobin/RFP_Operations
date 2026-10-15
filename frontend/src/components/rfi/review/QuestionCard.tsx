/** La question sélectionnée, en grand, avec ses actions (et leurs raccourcis clavier). */
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'
import { Ban, Check, ChevronDown, ChevronUp, Pencil, RotateCcw, Shuffle } from 'lucide-react'
import { texts } from '../../../content/texts'
import type { RfiFact, RfiQuestion } from '../../../lib/types'
import { DecisionBadge } from '../Decision'
import { STATE_STYLE, type Override, type ReviewState } from './state'

export interface QuestionCardHandle { edit: () => void; editWith: (value: string) => void; source: () => void }

const AUTO = '__auto__'

export const QuestionCard = forwardRef<QuestionCardHandle, {
  q: RfiQuestion; state: ReviewState; override: Override | undefined; facts: RfiFact[]; position: string
  onAccept: () => void; onOverride: (v: Override | undefined) => void; onPrev: () => void; onNext: () => void
}>(function QuestionCard({ q, state, override, facts, position, onAccept, onOverride, onPrev, onNext }, ref) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const input = useRef<HTMLInputElement & HTMLSelectElement>(null)
  const source = useRef<HTMLSelectElement>(null)
  useImperativeHandle(ref, () => ({ edit: () => setEditing(true), editWith: (value) => { setDraft(value); setEditing(true) }, source: () => source.current?.focus() }))
  useEffect(() => { setEditing(false); setDraft(typeof override === 'object' && override ? override.text : q.answer ?? '') }, [q.id]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (editing) input.current?.focus() }, [editing])

  const save = () => { onOverride({ text: draft }); setEditing(false) }
  const text = typeof override === 'object' && override ? override.text : q.answer
  return (
    <article className="rounded-[var(--radius-card)] border-[2.5px] border-fg bg-card p-5 shadow-[var(--shadow-pop)]">
      <div className="flex items-center justify-between gap-2 text-xs font-bold text-fg-3">
        <span>{texts.review.cell} {q.location}{q.entity?.isin ? ` · ${q.entity.isin}` : ''}</span>
        <span className="flex items-center gap-1">
          {position}
          <button onClick={onPrev} aria-label={texts.review.prev} className="rounded-full border-2 border-fg/30 p-0.5 hover:border-fg"><ChevronUp size={14} /></button>
          <button onClick={onNext} aria-label={texts.review.next} className="rounded-full border-2 border-fg/30 p-0.5 hover:border-fg"><ChevronDown size={14} /></button>
        </span>
      </div>
      {q.context && q.layout === 'list' && !/^[\d.\s]+$/.test(q.context) && <p className="mt-2 text-xs font-bold uppercase tracking-wider text-magic-300">{q.context}</p>}
      <h3 className="mt-1 text-xl leading-snug">{q.question}</h3>
      {q.hint && <p className="mt-2 inline-block rounded-lg border border-fg/20 bg-card-2 px-2 py-0.5 text-xs font-semibold text-fg-2">{texts.review.hint} : « {q.hint} »</p>}

      <div className={`mt-4 rounded-2xl border-[2.5px] border-fg p-4 ${STATE_STYLE[state]}`}>
        <p className="flex items-center justify-between gap-2 text-[0.7rem] font-bold uppercase tracking-wider">
          {texts.review.proposed}
          <span className="normal-case tracking-normal">{texts.review.legend[state] ?? texts.rfi.status[q.status]}</span>
        </p>
        {editing ? (
          <div className="mt-2 flex gap-2">
            {q.options.length > 0 ? (
              <select ref={input} value={draft} onChange={(e) => setDraft(e.target.value)} className="flex-1 rounded-xl border-2 border-fg bg-card px-2 py-1.5 font-semibold text-fg">
                <option value="">—</option>
                {q.options.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            ) : (
              <textarea ref={input as unknown as React.RefObject<HTMLTextAreaElement>} value={draft} onChange={(e) => setDraft(e.target.value)} rows={Math.min(8, Math.max(2, Math.ceil(draft.length / 60)))}
                onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey || draft.length < 80)) { e.preventDefault(); save() } if (e.key === 'Escape') setEditing(false) }}
                className="flex-1 resize-y rounded-xl border-2 border-fg bg-card px-2 py-1.5 font-semibold text-fg" placeholder={texts.rfi.freeTextPlaceholder} />
            )}
            <button onClick={save} className="rounded-full border-2 border-fg bg-card px-3 text-sm font-bold text-fg">{texts.review.save}</button>
          </div>
        ) : (
          <p className={`mt-1 whitespace-pre-line font-display font-bold leading-tight ${(text?.length ?? 0) > 120 ? 'text-lg' : 'text-3xl'}`}>{state === 'skipped' ? '—' : text ?? <span className="text-xl opacity-70">{q.suggestion ? `${q.suggestion} ?` : texts.review.none}</span>}</p>
        )}
        {q.precedent && <div className="mt-2"><DecisionBadge decision={q.precedent} /></div>}
      </div>
      {q.options.length > 0 && !editing && <p className="mt-2 text-xs font-semibold text-magic-300">{texts.review.options} : {q.options.slice(0, 10).join(' · ')}</p>}

      <div className="mt-4 flex flex-wrap gap-2">
        {q.answer != null && state === 'review' && (
          <button onClick={onAccept} className="inline-flex items-center gap-1.5 rounded-full border-[2.5px] border-fg bg-mint-400 px-4 py-1.5 font-bold shadow-[3px_3px_0_0_var(--color-fg)] transition-transform hover:-translate-y-0.5">
            <Check size={16} aria-hidden="true" />{texts.review.acceptNext} <kbd className="text-[0.65rem] opacity-70">A</kbd>
          </button>
        )}
        <button onClick={() => setEditing(true)} className="inline-flex items-center gap-1.5 rounded-full border-2 border-fg bg-card px-3.5 py-1.5 text-sm font-bold">
          <Pencil size={14} aria-hidden="true" />{texts.review.edit} <kbd className="text-[0.65rem] opacity-70">E</kbd>
        </button>
        <label className="inline-flex items-center gap-1.5 rounded-full border-2 border-fg bg-card px-3 py-1 text-sm font-bold">
          <Shuffle size={14} aria-hidden="true" /><span className="sr-only">{texts.review.source}</span>
          <select ref={source} value={typeof override === 'string' ? override : AUTO} onChange={(e) => onOverride(e.target.value === AUTO ? undefined : e.target.value)}
            className="max-w-[13rem] bg-transparent text-sm font-bold focus:outline-none">
            <option value={AUTO}>{texts.review.source} (S)</option>
            {q.alternatives.length > 0 && <optgroup label={texts.review.alternatives}>{q.alternatives.map((a) => <option key={a.concept} value={a.concept}>{a.label}{a.answer ? ` = ${a.answer}` : ''}</option>)}</optgroup>}
            {(['fund', 'share'] as const).map((scope) => (
              <optgroup key={scope} label={scope === 'fund' ? 'Fonds' : 'Part'}>{facts.filter((f) => f.scope === scope).map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}</optgroup>
            ))}
          </select>
        </label>
        {state === 'skipped' || override !== undefined ? (
          <button onClick={() => onOverride(undefined)} className="inline-flex items-center gap-1.5 rounded-full border-2 border-fg/40 px-3.5 py-1.5 text-sm font-bold">
            <RotateCcw size={14} aria-hidden="true" />{texts.review.restore}
          </button>
        ) : (
          <button onClick={() => onOverride(null)} className="inline-flex items-center gap-1.5 rounded-full border-2 border-fg/40 px-3.5 py-1.5 text-sm font-bold">
            <Ban size={14} aria-hidden="true" />{texts.review.ignore} <kbd className="text-[0.65rem] opacity-70">X</kbd>
          </button>
        )}
      </div>
    </article>
  )
})
