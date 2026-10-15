/**
 * Carrousel des sources : toutes les réponses possibles d'une case (Fabric, DIC / prospectus, anciens RFI, Qvidian,
 * Copilot…), une carte par réponse, à faire défiler pour comparer, avec « Choisir ».
 * L'ordre vient du serveur (merlin/rfi/aggregate.py) : réponses identiques ou versions d'un même texte regroupées,
 * puis classées par fréquence × récence × fiabilité de la source. La barre montre la part du score.
 * Clavier : ← / → quand le carrousel a le focus ; les filtres limitent aux cartes d'une source.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, BookOpen, Bot, Check, ChevronLeft, ChevronRight, Database, ExternalLink, FileText, History, Library, Lock, PenLine, Sparkles, Trophy } from 'lucide-react'
import { texts } from '../../../content/texts'
import type { RfiChoice, RfiChoiceSource, RfiQuestion } from '../../../lib/types'
import { prefersReducedMotion } from '../../../motion/tokens'
import type { Override } from './state'

const C = texts.carousel
const ICON: Record<string, typeof Database> = {
  fabric: Database, kid: FileText, prospectus: BookOpen, document: FileText, precedent: History, qvidian: Library, copilot: Bot,
  library: Check, mine: PenLine, app: Sparkles, alternative: Database,
}
const TONE: Record<string, string> = {
  fabric: 'bg-mint-400', kid: 'bg-magic-400/40', prospectus: 'bg-magic-400/40', document: 'bg-magic-400/40', precedent: 'bg-sun-400',
  qvidian: 'bg-magic-500 text-white', copilot: 'bg-bubble-400', library: 'bg-mint-400/60', mine: 'bg-fg text-canvas', app: 'bg-card-3', alternative: 'bg-card-3',
}
const FAMILY: Record<string, string> = { kid: 'document', prospectus: 'document', document: 'document', library: 'app', app: 'app' }
const family = (kind: string) => FAMILY[kind] ?? kind
const key = (v: string) => v.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').replace(/[.;:]+$/, '').trim()

interface Card extends RfiChoice { current: boolean; adapt: boolean; mine?: boolean }

function cardsFor(q: RfiQuestion, override: Override | undefined): Card[] {
  const mine = override && typeof override === 'object' ? override.text : null
  const current = mine ?? q.answer
  const list: Card[] = (q.choices ?? []).map((c) => ({
    ...c, current: !!current && key(current) === key(c.value),
    adapt: c.sources.length > 0 && c.sources.every((s) => s.blocked),
  }))
  if (mine && !list.some((c) => c.current)) {
    list.unshift({ value: mine, score: 0, share: 0, versions: 1, latest: null, uses: 1, why: C.mineWhy, current: true, adapt: false, mine: true,
      sources: [{ kind: 'mine', label: C.mine, url: '', check: null, blocked: false, date: null, uses: 1, ref: '' }] })
  }
  return list
}

function Chip({ s, count }: { s: RfiChoiceSource; count: number }) {
  const Icon = ICON[s.kind] ?? Database
  const name = C.kinds[s.kind] ?? s.kind
  const extra = s.kind === 'qvidian' && s.uses > 1 ? ` · ${C.uses(s.uses)}` : ''
  const label = `${name}${count > 1 ? ` ×${count}` : ''}${extra}`
  const body = (
    <>
      <Icon size={11} aria-hidden="true" className="shrink-0" />
      <span className="truncate">{label}</span>
      {s.check === 'match' && <Check size={10} aria-label={C.checked} />}
      {s.check === 'mismatch' && <AlertTriangle size={10} aria-label={C.differs} />}
      {s.blocked && <Lock size={10} aria-label={C.blocked} />}
    </>
  )
  const cls = `inline-flex max-w-full items-center gap-1 rounded-full border-2 border-fg px-2 py-0.5 text-[0.68rem] font-bold ${TONE[s.kind] ?? 'bg-card'}`
  return s.url
    ? <a href={s.url} target="_blank" rel="noreferrer" title={s.label} className={`${cls} hover:-translate-y-px`}>{body}<ExternalLink size={9} aria-hidden="true" /></a>
    : <span title={s.label} className={cls}>{body}</span>
}

export function SourceCarousel({ q, override, onChoose, onEdit }: {
  q: RfiQuestion; override: Override | undefined; onChoose: (value: string, adapt: boolean) => void; onEdit: (value: string) => void
}) {
  const all = useMemo(() => cardsFor(q, override), [q, override])
  const kinds = useMemo(() => [...new Set(all.flatMap((c) => c.sources.map((s) => family(s.kind))))], [all])
  const [filter, setFilter] = useState<string>('all')
  const [index, setIndex] = useState(0)
  const [open, setOpen] = useState<Record<number, boolean>>({})
  const track = useRef<HTMLDivElement>(null)
  const cards = filter === 'all' ? all : all.filter((c) => c.sources.some((s) => family(s.kind) === filter))

  useEffect(() => { setFilter('all'); setIndex(0); setOpen({}); track.current?.scrollTo({ left: 0 }) }, [q.id])
  useEffect(() => { if (!kinds.includes(filter)) setFilter('all') }, [kinds, filter])

  const go = (i: number) => {
    const n = Math.max(0, Math.min(cards.length - 1, i))
    setIndex(n)
    const el = track.current?.children[n] as HTMLElement | undefined
    if (el && track.current) track.current.scrollTo({ left: el.offsetLeft - track.current.offsetLeft, behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
  }
  const onScroll = () => {
    const t = track.current
    if (!t || !t.children.length) return
    const w = (t.children[0] as HTMLElement).offsetWidth + 12
    setIndex(Math.max(0, Math.min(cards.length - 1, Math.round(t.scrollLeft / w))))
  }

  if (all.length === 0) return <p className="text-sm font-semibold text-fg-2">{texts.review.noProposal}</p>

  return (
    <div className="flex flex-col gap-2" onKeyDown={(e) => {
      if (e.key === 'ArrowRight') { e.preventDefault(); e.stopPropagation(); go(index + 1) }
      if (e.key === 'ArrowLeft') { e.preventDefault(); e.stopPropagation(); go(index - 1) }
    }}>
      <div className="flex flex-wrap items-center gap-1.5">
        {kinds.length > 1 && (['all', ...kinds]).map((k) => (
          <button key={k} onClick={() => { setFilter(k); setIndex(0); track.current?.scrollTo({ left: 0 }) }} aria-pressed={filter === k}
            className={`rounded-full border-2 px-2.5 py-0.5 text-xs font-bold ${filter === k ? 'border-fg bg-sun-400' : 'border-fg/25 hover:border-fg'}`}>
            {k === 'all' ? C.all(all.length) : C.families[k] ?? k}
          </button>
        ))}
        <span className="ml-auto flex items-center gap-1">
          <span className="text-xs font-bold tabular-nums text-fg-2" aria-live="polite">{cards.length ? `${index + 1} / ${cards.length}` : '0'}</span>
          <button onClick={() => go(index - 1)} disabled={index === 0} aria-label={C.prev}
            className="rounded-full border-2 border-fg bg-card p-1 disabled:opacity-30"><ChevronLeft size={15} /></button>
          <button onClick={() => go(index + 1)} disabled={index >= cards.length - 1} aria-label={C.next}
            className="rounded-full border-2 border-fg bg-card p-1 disabled:opacity-30"><ChevronRight size={15} /></button>
        </span>
      </div>

      <div ref={track} onScroll={onScroll} tabIndex={0} role="group" aria-roledescription="carrousel" aria-label={C.label}
        className="flex snap-x snap-mandatory gap-3 overflow-x-auto pb-2 outline-none [scrollbar-width:thin] focus-visible:ring-2 focus-visible:ring-magic-400">
        {cards.map((c, i) => {
          const counts = new Map<string, { s: RfiChoiceSource; n: number }>()
          for (const s of c.sources) {
            const k = s.kind === 'precedent' || s.kind === 'qvidian' ? s.kind : `${s.kind}:${s.label}`
            const prev = counts.get(k)
            if (prev) { prev.n += 1; prev.s = { ...prev.s, uses: prev.s.uses + s.uses } } else counts.set(k, { s, n: 1 })
          }
          const long = c.value.length > 260
          const best = i === 0 && filter === 'all' && !c.mine && all.length > 1
          return (
            <article key={`${c.value}-${i}`} aria-roledescription="carte" aria-label={`${i + 1} / ${cards.length}`}
              className={`flex w-[88%] shrink-0 snap-start flex-col gap-2 rounded-2xl border-[2.5px] p-3 ${c.current ? 'border-fg bg-sun-400/25 shadow-[3px_3px_0_0_var(--color-fg)]' : 'border-fg/30 bg-card'}`}>
              <div className="flex items-center gap-2">
                {best ? (
                  <span className="inline-flex items-center gap-1 rounded-full border-2 border-fg bg-mint-400 px-2 py-0.5 text-[0.7rem] font-bold"><Trophy size={11} aria-hidden="true" />{C.best}</span>
                ) : <span className="text-[0.7rem] font-bold text-fg-3">#{i + 1}</span>}
                {!c.mine && (
                  <span className="flex flex-1 items-center gap-1.5" title={C.shareHint}>
                    <span className="h-2 flex-1 overflow-hidden rounded-full border border-fg/40 bg-card-2">
                      <span className="block h-full bg-magic-400" style={{ width: `${Math.max(4, Math.round(c.share * 100))}%` }} />
                    </span>
                    <span className="text-[0.7rem] font-bold tabular-nums">{Math.round(c.share * 100)} %</span>
                  </span>
                )}
                {c.current && <span className="ml-auto inline-flex items-center gap-1 rounded-full border-2 border-fg bg-mint-400 px-2 py-0.5 text-[0.7rem] font-bold"><Check size={11} aria-hidden="true" />{texts.review.kept}</span>}
              </div>
              <p className={`whitespace-pre-line font-semibold ${long ? 'text-sm' : 'font-display text-lg leading-snug'}`}>
                {long && !open[i] ? `${c.value.slice(0, 260)}…` : c.value}
              </p>
              {long && (
                <button onClick={() => setOpen((o) => ({ ...o, [i]: !o[i] }))} className="self-start text-xs font-bold text-magic-300 underline">
                  {open[i] ? C.less : C.more}
                </button>
              )}
              <div className="flex flex-wrap gap-1">
                {[...counts.values()].slice(0, 6).map(({ s, n }, j) => <Chip key={`${s.kind}-${j}`} s={s} count={n} />)}
              </div>
              {!c.mine && <p className="text-[0.7rem] font-semibold text-fg-2">{c.why}</p>}
              {c.adapt && <p className="flex items-center gap-1 text-[0.7rem] font-bold text-warning"><AlertTriangle size={12} aria-hidden="true" />{texts.review.adaptNote}</p>}
              <div className="mt-auto flex flex-wrap gap-2 pt-1">
                {!c.current && (
                  <button onClick={() => onChoose(c.value, c.adapt)}
                    className="rounded-full border-2 border-fg bg-sun-400 px-3.5 py-1 text-sm font-bold shadow-[2px_2px_0_0_var(--color-fg)] transition-transform hover:-translate-y-0.5">
                    {c.adapt ? texts.review.chooseAdapt : texts.review.choose}
                  </button>
                )}
                <button onClick={() => onEdit(c.value)} className="rounded-full border-2 border-fg/40 px-3 py-1 text-xs font-bold hover:border-fg">{C.editFirst}</button>
              </div>
            </article>
          )
        })}
      </div>

      {cards.length > 1 && (
        <div className="flex justify-center gap-1.5" role="tablist" aria-label={C.label}>
          {cards.map((c, i) => (
            <button key={i} role="tab" aria-selected={i === index} aria-label={`${i + 1}`} onClick={() => go(i)}
              className={`size-2.5 rounded-full border border-fg ${i === index ? 'bg-fg' : TONE[c.sources[0]?.kind ?? ''] ?? 'bg-card'}`} />
          ))}
        </div>
      )}
    </div>
  )
}
