/** Les preuves d'une réponse : incohérences d'abord, puis Fabric, documents officiels, anciens RFI, raisonnement. */
import { AlertTriangle, BookOpen, Database, ExternalLink, FileText, History, Lock } from 'lucide-react'
import { texts } from '../../../content/texts'
import type { RfiQuestion, RfiSource } from '../../../lib/types'
import { DecisionDetail } from '../Decision'

const ICON: Record<string, typeof Database> = { fabric: Database, kid: FileText, prospectus: BookOpen, document: FileText, precedent: History }
const CHECK: Record<string, string> = { match: 'bg-mint-400', mismatch: 'bg-bubble-400 text-white', fill: 'bg-sun-400', unknown: 'bg-card-2' }

function Source({ s, onUse }: { s: RfiSource; onUse?: (value: string) => void }) {
  const Icon = ICON[s.kind] ?? FileText
  return (
    <li className="rounded-xl border-2 border-fg bg-card p-2.5">
      <p className="flex flex-wrap items-center gap-1.5 text-xs font-bold">
        <Icon size={14} aria-hidden="true" />
        <span>{texts.review.sourceKind[s.kind] ?? s.kind}</span>
        {s.check && <span className={`rounded-full border-2 border-fg px-2 py-px text-[0.65rem] ${CHECK[s.check] ?? 'bg-card-2'}`}>{texts.review.check[s.check] ?? s.check}</span>}
        {s.blocked && <span className="inline-flex items-center gap-1 text-bubble-300"><Lock size={11} aria-hidden="true" />{texts.rfi.blocked}</span>}
      </p>
      {s.value && <p className="mt-1 font-display text-base font-semibold">{s.value}</p>}
      {s.detail && <p className="text-xs font-semibold text-fg-2">{texts.rfi.fabricSays} : {s.detail}</p>}
      {s.snippet && <p className="mt-1 rounded-lg bg-card-2 px-2 py-1 text-xs italic text-fg-2">« {s.snippet} »</p>}
      <p className="mt-1 text-[0.7rem] font-semibold text-fg-3">
        {s.url ? <a href={s.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 underline">{s.label}<ExternalLink size={10} aria-hidden="true" /></a> : s.label}
        {s.date ? ` · ${s.date}` : ''}
      </p>
      {onUse && s.value && (s.check === 'mismatch' || s.check === 'fill' || s.kind === 'fabric') && (
        <button onClick={() => onUse(s.value!)} className="mt-1.5 rounded-full border-2 border-fg px-2.5 py-0.5 text-[0.7rem] font-bold hover:bg-sun-400">
          {texts.review.use}
        </button>
      )}
    </li>
  )
}

export function EvidencePanel({ q, onUse }: { q: RfiQuestion | null; onUse?: (value: string) => void }) {
  if (!q) return null
  const sources = (q.sources ?? []).filter((s) => s.kind !== 'precedent')
  const conflict = q.issues.filter((i) => i.startsWith('incohérence'))
  const other = q.issues.filter((i) => !i.startsWith('incohérence'))
  return (
    <div className="flex flex-col gap-3">
      {conflict.length > 0 && (
        <div role="alert" className="rounded-xl border-2 border-fg bg-bubble-400 p-2.5 text-sm font-bold text-white">
          {conflict.map((c) => <p key={c} className="flex gap-1.5"><AlertTriangle size={16} className="shrink-0" aria-hidden="true" />{c}</p>)}
        </div>
      )}
      <section>
        <h4 className="text-xs font-bold uppercase tracking-wider text-fg-3">{texts.review.evidence}</h4>
        {sources.length > 0 ? <ul className="mt-1.5 flex flex-col gap-2">{sources.map((s, i) => <Source key={`${s.kind}-${i}`} s={s} onUse={sources.some((x) => x.check === 'mismatch') ? onUse : undefined} />)}</ul>
          : !q.precedent && <p className="mt-1 text-sm font-semibold text-fg-2">{texts.review.noEvidence}</p>}
      </section>
      {q.precedent && <DecisionDetail decision={q.precedent} />}
      {other.length > 0 && (
        <section>
          <h4 className="text-xs font-bold uppercase tracking-wider text-fg-3">{texts.review.issues}</h4>
          <ul className="mt-1 space-y-0.5 text-xs font-semibold text-warning">{other.map((i) => <li key={i}>⚠ {i}</li>)}</ul>
        </section>
      )}
      {(q.reasons.length > 0 || q.understanding.length > 0) && (
        <details className="text-xs font-semibold text-fg-2">
          <summary className="cursor-pointer font-bold text-magic-300">{texts.review.why}</summary>
          {q.concept_label && <p className="mt-1">{q.concept_label} · {Math.round(q.confidence * 100)} %</p>}
          <ul className="mt-1 list-disc pl-4">{q.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          {q.understanding.length > 0 && <p className="mt-1 text-fg-3">{q.understanding.join(' · ')}</p>}
        </details>
      )}
      {q.alternatives.length > 0 && (
        <details className="text-xs font-semibold text-fg-2">
          <summary className="cursor-pointer font-bold text-magic-300">{texts.review.alternatives}</summary>
          <ul className="mt-1 list-disc pl-4">{q.alternatives.map((a) => <li key={a.concept}>{a.label}{a.answer ? ` = ${a.answer}` : ''}</li>)}</ul>
        </details>
      )}
    </div>
  )
}
