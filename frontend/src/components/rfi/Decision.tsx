/** Décision justifiée d'une question : repris de l'ancien, modèle d'ontologie ou incohérence, avec les précédents contrôlés. */
import { useState } from 'react'
import { AlertTriangle, History, Lock, Sparkles } from 'lucide-react'
import { texts } from '../../content/texts'
import type { RfiDecision, RfiDecisionKind } from '../../lib/types'

const STYLE: Record<RfiDecisionKind, string> = {
  precedent_confirme: 'bg-mint-400',
  precedent_liaison: 'bg-magic-400 text-white',
  precedent_constant: 'bg-magic-400 text-white',
  precedent_habituel: 'bg-card-2',
  precedent_meme_fonds: 'bg-magic-400 text-white',
  modele_redaction: 'bg-card-2',
  incoherence: 'bg-bubble-400 text-white motion-safe:animate-[wiggle_0.6s_ease-in-out_2]',
  ontologie: 'bg-sun-400',
  aucun: 'bg-card',
}

const CHECK_STYLE: Record<string, string> = { match: 'text-mint-300', mismatch: 'text-bubble-300', unknown: 'text-fg-3' }

export function DecisionBadge({ decision }: { decision: RfiDecision }) {
  const Icon = decision.kind === 'incoherence' ? AlertTriangle : decision.kind.startsWith('precedent') ? History : Sparkles
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border-2 border-fg px-2.5 py-0.5 text-xs font-bold ${STYLE[decision.kind]}`}>
      <Icon size={12} aria-hidden="true" />{texts.rfi.decision[decision.kind] ?? decision.label}
    </span>
  )
}

export function DecisionDetail({ decision }: { decision: RfiDecision }) {
  const [open, setOpen] = useState(decision.kind === 'incoherence')
  const shown = decision.precedents.slice(0, 5)
  return (
    <div className="mt-2 rounded-xl border-2 border-fg/25 bg-card-2 p-2 text-xs font-semibold text-fg-2">
      <p><DecisionBadge decision={decision} /> <span className="ml-1">{decision.justification}</span></p>
      {decision.template && <p className="mt-1 text-fg-3"><b>{texts.rfi.templateLabel} :</b> {decision.template}</p>}
      {shown.length > 0 && (
        <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="mt-1 font-bold text-magic-300 underline decoration-2 underline-offset-2">
          {texts.rfi.precedentsTitle} ({decision.precedents.length})
        </button>
      )}
      {open && (
        <ul className="mt-1 space-y-1.5">
          {shown.map((p) => (
            <li key={p.id} className="rounded-lg border border-fg/15 bg-card px-2 py-1">
              <p className="text-fg">« {p.answer.slice(0, 160)}{p.answer.length > 160 ? '…' : ''} »</p>
              <p className="text-[0.7rem] text-fg-3">
                {p.url ? <a href={p.url} target="_blank" rel="noreferrer" className="underline">{p.provenance}</a> : p.provenance}
                {' · '}{texts.rfi.similarity(p.similarity)}
              </p>
              {p.blocked && <p className="text-[0.7rem] text-bubble-300"><Lock size={10} className="inline" aria-hidden="true" /> {texts.rfi.blocked} — {p.block_reason}</p>}
              {p.check && (
                <p className={`text-[0.7rem] ${CHECK_STYLE[p.check]}`}>
                  {texts.rfi.check[p.check]}{p.fabric ? ` · ${texts.rfi.fabricSays} : ${p.fabric}` : ''}{p.evidence ? ` (${p.evidence})` : ''}
                </p>
              )}
              {p.comments.length > 0 && <p className="text-[0.7rem] text-fg-3">💬 {p.comments.join(' · ').slice(0, 140)}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
