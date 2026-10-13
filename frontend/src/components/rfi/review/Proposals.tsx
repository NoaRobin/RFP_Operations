/**
 * Toutes les réponses possibles pour la case, côte à côte, chacune avec « Choisir » : la proposition de l'app, Fabric,
 * DIC / prospectus, Copilot, les anciens RFI, les autres données. Les réponses identiques sont fusionnées : on voit
 * d'un coup d'œil qui est d'accord avec qui (« 3 anciens RFI + DIC »).
 */
import { AlertTriangle, BookOpen, Bot, Check, Database, ExternalLink, FileText, History, Lock, PenLine, Sparkles } from 'lucide-react'
import { texts } from '../../../content/texts'
import type { RfiQuestion } from '../../../lib/types'
import type { Override } from './state'

type Kind = 'app' | 'fabric' | 'kid' | 'prospectus' | 'document' | 'copilot' | 'precedent' | 'alternative' | 'mine'

interface Origin { kind: Kind; label: string; url?: string; check?: string; blocked?: boolean; note?: string }
export interface Proposal { value: string; origins: Origin[]; current: boolean; adapt: boolean }

const ICON: Record<Kind, typeof Database> = {
  app: Sparkles, fabric: Database, kid: FileText, prospectus: BookOpen, document: FileText, copilot: Bot, precedent: History,
  alternative: Database, mine: PenLine,
}
const R = texts.review

const key = (v: string) => v.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').replace(/[.;:]+$/, '').trim()

export function buildProposals(q: RfiQuestion, override: Override | undefined): Proposal[] {
  const byKey = new Map<string, Proposal>()
  const mine = typeof override === 'object' && override ? override.text : null
  const add = (value: string | null | undefined, origin: Origin) => {
    const v = (value ?? '').trim()
    if (!v || v === '—') return
    const k = key(v)
    const p = byKey.get(k)
    if (p) {
      // La proposition de l'app qui vient de Fabric : la source Fabric (plus précise) la remplace, pas de doublon
      if (origin.kind === 'fabric') p.origins = p.origins.filter((o) => o.kind !== 'app')
      if (!p.origins.some((o) => o.kind === origin.kind && o.label === origin.label)) p.origins.push(origin)
      p.adapt = p.adapt && !!origin.blocked
    } else {
      byKey.set(k, { value: v, origins: [origin], current: false, adapt: !!origin.blocked })
    }
  }
  if (mine) add(mine, { kind: 'mine', label: R.yours })
  if (q.answer && q.source !== 'Copilot') add(q.answer, { kind: 'app', label: q.evidence || q.source || R.app })
  for (const s of q.sources ?? []) {
    if (s.kind === 'precedent') continue
    add(s.value, { kind: (s.kind as Kind) in ICON ? (s.kind as Kind) : 'document', label: s.label + (s.date ? ` · ${s.date}` : ''), url: s.url, check: s.check ?? undefined })
  }
  for (const p of q.precedent?.precedents ?? []) {
    add(p.answer, { kind: 'precedent', label: p.provenance, url: p.url, check: p.check ?? undefined, blocked: p.blocked, note: p.block_reason })
  }
  for (const a of q.alternatives) add(a.answer, { kind: 'alternative', label: a.label })
  const current = mine ?? q.answer
  const list = [...byKey.values()]
  for (const p of list) p.current = !!current && key(current) === key(p.value)
  // La retenue d'abord, puis les plus soutenues (plusieurs sources d'accord), puis celles vérifiées
  const score = (p: Proposal) => (p.current ? 1000 : 0) + p.origins.length * 10 + (p.origins.some((o) => o.check === 'match') ? 5 : 0)
    - (p.adapt ? 3 : 0)
  return list.sort((a, b) => score(b) - score(a))
}

function OriginChip({ o }: { o: Origin }) {
  const Icon = ICON[o.kind]
  const tone = o.check === 'match' ? 'border-mint-300' : o.check === 'mismatch' ? 'border-bubble-300' : 'border-fg/25'
  const label = o.kind === 'precedent' ? `${R.oldRfi} · ${o.label}` : o.kind === 'mine' || o.kind === 'app' ? o.label : `${R.sourceKind[o.kind] ?? R.other} · ${o.label}`
  const body = <><Icon size={11} aria-hidden="true" className="shrink-0" /><span className="truncate">{label}</span>{o.check && <span className="text-fg-3">· {R.check[o.check] ?? o.check}</span>}{o.blocked && <Lock size={10} aria-hidden="true" />}</>
  const cls = `inline-flex max-w-full items-center gap-1 rounded-full border-2 ${tone} bg-card px-2 py-0.5 text-[0.7rem] font-semibold`
  return o.url ? <a href={o.url} target="_blank" rel="noreferrer" title={o.label} className={`${cls} hover:border-fg`}>{body}<ExternalLink size={10} aria-hidden="true" /></a>
    : <span className={cls} title={o.note || o.label}>{body}</span>
}

export function Proposals({ q, override, onChoose }: {
  q: RfiQuestion; override: Override | undefined; onChoose: (value: string, adapt: boolean) => void
}) {
  const list = buildProposals(q, override)
  if (list.length === 0) return <p className="text-sm font-semibold text-fg-2">{R.noProposal}</p>
  return (
    <ul className="flex flex-col gap-2">
      {list.map((p) => {
        const precedents = p.origins.filter((o) => o.kind === 'precedent').length
        const long = p.value.length > 220
        return (
          <li key={p.value} className={`rounded-2xl border-2 p-3 ${p.current ? 'border-fg bg-sun-400/25' : 'border-fg/25 bg-card'}`}>
            <div className="flex items-start gap-3">
              <div className="min-w-0 flex-1">
                <p className={`whitespace-pre-line font-semibold ${long ? 'text-sm' : 'font-display text-lg leading-snug'}`}>{long ? `${p.value.slice(0, 600)}${p.value.length > 600 ? '…' : ''}` : p.value}</p>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {precedents > 1 && <span className="rounded-full border-2 border-fg bg-magic-400 px-2 py-0.5 text-[0.7rem] font-bold text-white">{R.consensus(precedents)}</span>}
                  {p.origins.slice(0, 4).map((o, i) => <OriginChip key={`${o.kind}-${i}`} o={o} />)}
                  {p.origins.length > 4 && <span className="text-[0.7rem] font-semibold text-fg-3">+{p.origins.length - 4}</span>}
                </div>
                {p.adapt && <p className="mt-1 flex items-center gap-1 text-[0.7rem] font-bold text-warning"><AlertTriangle size={12} aria-hidden="true" />{R.adaptNote}</p>}
              </div>
              {p.current ? (
                <span className="inline-flex shrink-0 items-center gap-1 rounded-full border-2 border-fg bg-mint-400 px-2.5 py-1 text-xs font-bold"><Check size={13} aria-hidden="true" />{R.kept}</span>
              ) : (
                <button onClick={() => onChoose(p.value, p.adapt)}
                  className="shrink-0 rounded-full border-2 border-fg bg-card px-3 py-1 text-xs font-bold shadow-[2px_2px_0_0_var(--color-fg)] transition-transform hover:-translate-y-0.5 hover:bg-sun-400">
                  {p.adapt ? R.chooseAdapt : R.choose}
                </button>
              )}
            </div>
          </li>
        )
      })}
    </ul>
  )
}
