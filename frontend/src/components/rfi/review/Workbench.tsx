/**
 * Atelier de revue : le document en grand à gauche (zoom, plein écran), la question et toutes ses propositions à droite,
 * chacune avec « Choisir ». Une barre fixe en bas : où on en est, Copilot, et « Générer » toujours à portée de main.
 * Clavier : J / K naviguer, A valider et suivant, E modifier, S autre donnée, X ne pas remplir (jamais pendant la saisie).
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Bot, CheckCheck, Keyboard, Maximize2, Minimize2, Minus, Plus, Sparkles } from 'lucide-react'
import { texts } from '../../../content/texts'
import type { RfiAnalysis, RfiFact, RfiPreview } from '../../../lib/types'
import { EvidencePanel } from './EvidencePanel'
import { ProgressRing } from './ProgressRing'
import { Proposals } from './Proposals'
import { QuestionCard, type QuestionCardHandle } from './QuestionCard'
import { QuestionList } from './QuestionList'
import { SheetPreview } from './SheetPreview'
import { reviewState, type Override, type ReviewState } from './state'

type Filter = 'todo' | 'review' | 'auto' | 'none' | 'all'
const R = texts.review
const ZOOM_KEY = 'rfppasenvie.rfi.zoom'
const norm = (v: string) => v.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim()

function savedZoom(): number {
  try { return Number(window.localStorage.getItem(ZOOM_KEY)) || 15 } catch { return 15 }
}

export function Workbench({ analysis, preview, facts, overrides, accepted, onAccept, onAcceptMany, onResetAccepted, onOverride, toWrite, generating, onGenerate, onCopilot }: {
  analysis: RfiAnalysis; preview: RfiPreview | null; facts: RfiFact[]; overrides: Record<string, Override>; accepted: Set<string>
  onAccept: (id: string, on: boolean) => void; onAcceptMany: (ids: string[]) => void; onResetAccepted: () => void; onOverride: (id: string, v: Override | undefined) => void
  toWrite: number; generating: boolean; onGenerate: () => void; onCopilot: () => void
}) {
  const hasSheet = !!preview && (preview.kind === 'docx' ? preview.items.length > 0 : preview.sheets.length > 0)
  const [tab, setTab] = useState<'document' | 'list'>(hasSheet ? 'document' : 'list')
  const [filter, setFilter] = useState<Filter>('todo')
  const [selected, setSelected] = useState<string | null>(null)
  const [zoom, setZoom] = useState(savedZoom)
  const [full, setFull] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const card = useRef<QuestionCardHandle>(null)

  useEffect(() => { if (hasSheet) setTab('document') }, [hasSheet])
  useEffect(() => { try { window.localStorage.setItem(ZOOM_KEY, String(zoom)) } catch { /* préférence locale facultative */ } }, [zoom])
  useEffect(() => {
    const onChange = () => setFull(document.fullscreenElement === root.current)
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])

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
  const todo = counts.review + counts.none

  useEffect(() => { if (!selected || !byId[selected]) setSelected(visible[0]?.id ?? analysis.questions[0]?.id ?? null) }, [analysis]) // eslint-disable-line react-hooks/exhaustive-deps

  const move = (step: number) => {
    if (order.length === 0) return
    setSelected(order[(Math.max(index, 0) + step + order.length) % order.length].id)
  }
  /** Suivante à traiter (pas simplement la suivante) : c'est ce qui fait gagner du temps. */
  const nextTodo = () => {
    const list = analysis.questions
    const start = Math.max(list.findIndex((q) => q.id === selected), 0)
    for (let i = 1; i <= list.length; i++) {
      const q = list[(start + i) % list.length]
      if (q.id !== selected && (states[q.id] === 'review' || states[q.id] === 'none')) { setSelected(q.id); return }
    }
    move(1)
  }
  const acceptAndNext = () => {
    if (selected && states[selected] === 'review') onAccept(selected, true)
    nextTodo()
  }
  const q = selected ? byId[selected] : null
  const choose = (value: string, adapt: boolean) => {
    if (!q) return
    const option = q.options.length ? q.options.find((o) => norm(o) === norm(value)) : value
    if (adapt || option === undefined) { card.current?.editWith(option ?? value); return }  // à adapter, ou hors liste du client
    onOverride(q.id, { text: option })
    nextTodo()
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (e.metaKey || e.ctrlKey || e.altKey || ['INPUT', 'SELECT', 'TEXTAREA'].includes(t.tagName) || t.isContentEditable) return
      const k = e.key.toLowerCase()
      if (k === 'j' || e.key === 'ArrowDown') { e.preventDefault(); move(1) }
      else if (k === 'k' || e.key === 'ArrowUp') { e.preventDefault(); move(-1) }
      else if (k === 'a' && e.shiftKey) { e.preventDefault(); onAcceptMany(analysis.questions.filter((x) => states[x.id] === 'review').map((x) => x.id)) }
      else if (k === 'a') { e.preventDefault(); acceptAndNext() }
      else if (k === 'e') { e.preventDefault(); card.current?.edit() }
      else if (k === 's') { e.preventDefault(); card.current?.source() }
      else if (k === 'x' && selected) { e.preventDefault(); onOverride(selected, null); nextTodo() }
      else if (k === '+' || k === '=') setZoom((z) => Math.min(22, z + 1))
      else if (k === '-') setZoom((z) => Math.max(10, z - 1))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const toggleFull = () => {
    if (document.fullscreenElement) void document.exitFullscreen()
    else void root.current?.requestFullscreen?.()
  }
  const docConfirmed = analysis.questions.filter((x) => states[x.id] === 'review' && (x.sources ?? []).some((s) => (s.kind === 'kid' || s.kind === 'prospectus') && s.check === 'match')).map((x) => x.id)
  const firm = analysis.questions.filter((x) => states[x.id] === 'review' && x.precedent?.kind === 'precedent_constant').map((x) => x.id)
  const allReview = analysis.questions.filter((x) => states[x.id] === 'review').map((x) => x.id)
  const visibleReview = visible.filter((x) => states[x.id] === 'review').map((x) => x.id)
  const validated = analysis.questions.filter((x) => accepted.has(x.id) && states[x.id] === 'accepted').length
  const height = full ? 'h-[calc(100vh-7.5rem)]' : 'xl:h-[calc(100vh-11rem)]'

  return (
    <div ref={root} className={`flex flex-col gap-3 ${full ? 'overflow-auto bg-canvas p-4' : ''}`}>
      <div className="flex flex-wrap items-center gap-3 rounded-2xl border-2 border-fg bg-card-2 px-4 py-2.5">
        <ProgressRing counts={counts} />
        <div className="flex flex-wrap items-center gap-2">
          {allReview.length > 0 ? (
            <button onClick={() => onAcceptMany(allReview)} title={R.validateAllHint}
              className="inline-flex items-center gap-1.5 rounded-full border-[2.5px] border-fg bg-mint-400 px-4 py-1.5 font-bold shadow-[3px_3px_0_0_var(--color-fg)] transition-transform hover:-translate-y-0.5">
              <CheckCheck size={16} aria-hidden="true" />{R.validateAll(allReview.length)} <kbd className="text-[0.65rem] opacity-70">⇧A</kbd>
            </button>
          ) : <span className="text-sm font-bold text-mint-300">✓ {R.nothingToValidate}</span>}
          {tab === 'list' && filter !== 'todo' && filter !== 'review' && visibleReview.length > 0 && visibleReview.length < allReview.length && (
            <BulkButton label={R.bulkVisible(visibleReview.length)} onClick={() => onAcceptMany(visibleReview)} />
          )}
          {docConfirmed.length > 0 && docConfirmed.length < allReview.length && <BulkButton label={R.bulkDocs(docConfirmed.length)} onClick={() => onAcceptMany(docConfirmed)} />}
          {firm.length > 0 && firm.length < allReview.length && <BulkButton label={R.bulkFirm(firm.length)} onClick={() => onAcceptMany(firm)} />}
          {validated > 0 && (
            <button onClick={onResetAccepted} className="rounded-full border-2 border-fg/30 px-3 py-1 text-xs font-bold text-fg-2 hover:border-fg">{R.undoValidations(validated)}</button>
          )}
          {counts.none > 0 && <span className="text-xs font-semibold text-fg-3">{R.stillEmpty(counts.none)}</span>}
        </div>
        <p className="ml-auto hidden items-center gap-1.5 text-xs font-semibold text-fg-3 2xl:flex"><Keyboard size={14} aria-hidden="true" />{R.shortcuts}</p>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.75fr)_minmax(26rem,1fr)]">
        <section className={`flex min-h-[32rem] flex-col rounded-[var(--radius-card)] border-2 border-fg bg-card p-3 xl:sticky xl:top-24 ${height}`}>
          <div className="mb-2 flex flex-wrap items-center gap-1.5">
            {(['document', 'list'] as const).map((t) => (
              <button key={t} onClick={() => setTab(t)} aria-pressed={tab === t} disabled={t === 'document' && !hasSheet}
                className={`rounded-full border-2 px-3 py-0.5 text-sm font-bold disabled:opacity-40 ${tab === t ? 'border-fg bg-magic-500 text-white' : 'border-fg/30'}`}>{R.tabs[t]}</button>
            ))}
            {tab === 'list' && (
              <span className="flex flex-wrap gap-1">
                {(['todo', 'review', 'none', 'auto', 'all'] as Filter[]).map((f) => (
                  <button key={f} onClick={() => setFilter(f)} aria-pressed={filter === f}
                    className={`rounded-full border px-2 py-px text-xs font-bold ${filter === f ? 'border-fg bg-sun-400' : 'border-fg/25'}`}>{R.filters[f]}</button>
                ))}
              </span>
            )}
            <span className="ml-auto flex items-center gap-1">
              <button onClick={() => setZoom((z) => Math.max(10, z - 1))} aria-label={R.zoomOut} title={`${R.zoomOut} (−)`} className="rounded-full border-2 border-fg/30 p-1 hover:border-fg"><Minus size={14} /></button>
              <span className="w-10 text-center text-xs font-bold tabular-nums">{Math.round((zoom / 15) * 100)} %</span>
              <button onClick={() => setZoom((z) => Math.min(22, z + 1))} aria-label={R.zoomIn} title={`${R.zoomIn} (+)`} className="rounded-full border-2 border-fg/30 p-1 hover:border-fg"><Plus size={14} /></button>
              <button onClick={toggleFull} aria-label={full ? R.exitFull : R.full} title={full ? R.exitFull : R.full} className="ml-1 rounded-full border-2 border-fg/30 p-1 hover:border-fg">
                {full ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
              </button>
            </span>
          </div>
          <div className="min-h-0 flex-1 overflow-auto">
            {tab === 'document' && preview ? (
              <SheetPreview preview={preview} questions={byId} states={states} selected={selected} onSelect={setSelected} zoom={zoom} />
            ) : (
              <QuestionList questions={visible} states={states} selected={selected} onSelect={setSelected} />
            )}
          </div>
        </section>

        <section className={`flex min-w-0 flex-col gap-3 xl:overflow-auto xl:pr-1 ${height}`}>
          {q ? (
            <>
              <QuestionCard ref={card} q={q} state={states[q.id]} override={overrides[q.id]} facts={facts}
                position={`${index + 1} / ${order.length}`} onPrev={() => move(-1)} onNext={() => move(1)}
                onAccept={acceptAndNext} onOverride={(v) => onOverride(q.id, v)} />
              <div className="rounded-[var(--radius-card)] border-2 border-fg/25 bg-card-2 p-3">
                <h4 className="mb-2 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-fg-3"><Sparkles size={13} aria-hidden="true" />{R.proposals}</h4>
                <Proposals q={q} override={overrides[q.id]} onChoose={choose} />
              </div>
              <EvidencePanel q={q} />
            </>
          ) : <p className="font-semibold text-fg-2">{R.pick}</p>}
        </section>
      </div>

      <div className="sticky bottom-3 z-30 flex flex-wrap items-center gap-3 rounded-2xl border-[2.5px] border-fg bg-card px-4 py-2.5 shadow-[var(--shadow-pop)]">
        <p className="text-sm font-bold">{todo > 0 ? R.remaining(todo) : R.allDone}</p>
        <button onClick={nextTodo} disabled={todo === 0} className="rounded-full border-2 border-fg/40 px-3 py-1 text-sm font-bold hover:border-fg disabled:opacity-40">{R.nextTodo}</button>
        <span className="ml-auto flex flex-wrap items-center gap-2">
          <button onClick={onCopilot} className="inline-flex items-center gap-1.5 rounded-full border-2 border-fg bg-card px-3.5 py-1.5 text-sm font-bold hover:bg-magic-400 hover:text-white">
            <Bot size={16} aria-hidden="true" />{R.askCopilot}
          </button>
          <button onClick={onGenerate} disabled={toWrite === 0 || generating}
            className="inline-flex items-center gap-1.5 rounded-full border-[2.5px] border-fg bg-sun-400 px-5 py-1.5 font-display text-base font-semibold shadow-[3px_3px_0_0_var(--color-fg)] transition-transform hover:-translate-y-0.5 disabled:opacity-50">
            {generating ? texts.rfi.generating : R.generate(toWrite)}
          </button>
        </span>
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
