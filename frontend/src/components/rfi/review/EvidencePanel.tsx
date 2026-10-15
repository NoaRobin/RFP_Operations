/** Ce qui aide à trancher, sous les propositions : incohérences d'abord, puis points d'attention, extraits des documents,
 * justification des anciens RFI et raisonnement de l'app (replié). Les valeurs elles-mêmes sont dans « Propositions ». */
import { AlertTriangle } from 'lucide-react'
import { texts } from '../../../content/texts'
import type { RfiQuestion } from '../../../lib/types'

export function EvidencePanel({ q }: { q: RfiQuestion | null }) {
  if (!q) return null
  const conflict = q.issues.filter((i) => i.startsWith('incohérence'))
  const other = q.issues.filter((i) => !i.startsWith('incohérence'))
  const excerpts = (q.sources ?? []).filter((s) => s.snippet)
  return (
    <div className="flex flex-col gap-3">
      {conflict.length > 0 && (
        <div role="alert" className="rounded-xl border-2 border-fg bg-bubble-400 p-2.5 text-sm font-bold text-white">
          {conflict.map((c) => <p key={c} className="flex gap-1.5"><AlertTriangle size={16} className="shrink-0" aria-hidden="true" />{c}</p>)}
        </div>
      )}
      {other.length > 0 && <ul className="space-y-0.5 text-xs font-semibold text-warning">{other.map((i) => <li key={i}>⚠ {i}</li>)}</ul>}
      {excerpts.length > 0 && (
        <section>
          <h4 className="text-xs font-bold uppercase tracking-wider text-fg-3">{texts.review.excerpts}</h4>
          <ul className="mt-1 space-y-1">
            {excerpts.map((s, i) => (
              <li key={i} className="rounded-lg bg-card-2 px-2 py-1 text-xs text-fg-2">
                <span className="italic">« {s.snippet} »</span> <span className="font-semibold text-fg-3">— {s.label}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {q.precedent?.justification && <p className="text-xs font-semibold text-fg-2">{q.precedent.justification}</p>}
      {(q.reasons.length > 0 || q.understanding.length > 0) && (
        <details className="text-xs font-semibold text-fg-2">
          <summary className="cursor-pointer font-bold text-magic-300">{texts.review.why}</summary>
          {q.concept_label && <p className="mt-1">{q.concept_label} · {Math.round(q.confidence * 100)} %</p>}
          <ul className="mt-1 list-disc pl-4">{q.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          {q.understanding.length > 0 && <p className="mt-1 text-fg-3">{q.understanding.join(' · ')}</p>}
        </details>
      )}
    </div>
  )
}
