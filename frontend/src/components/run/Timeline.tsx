import { useEffect, useRef } from 'react'
import { Check, X } from 'lucide-react'
import { texts } from '../../content/texts'
import { formatDuration } from '../../lib/format'
import { gsap } from '../../motion/gsap'
import { d, ease } from '../../motion/tokens'
import type { StepState } from './useRunStream'

function StepNode({ step, index }: { step: StepState; index: number }) {
  const node = useRef<HTMLSpanElement>(null)
  const previous = useRef(step.status)
  useEffect(() => {
    if (previous.current !== step.status && node.current) {
      gsap.fromTo(node.current, { scale: 0.5 }, { scale: 1, duration: d('slow'), ease: ease.spring })
    }
    previous.current = step.status
  }, [step.status])

  const styles = {
    pending: 'border-line-strong text-haze bg-ink',
    running: 'border-arcane-400 text-arcane-300 bg-arcane-400/10 animate-pulse-glow',
    done: 'border-gold-400 text-abyss bg-gold-300 shadow-[0_0_16px_rgb(232_199_122/0.6)]',
    error: 'border-danger text-parchment bg-danger/70',
  }[step.status]

  return (
    <li className="relative flex gap-4 pb-6 last:pb-0">
      <span ref={node} className={`relative z-10 grid size-8 shrink-0 place-items-center rounded-full border-2 font-mono text-xs font-bold ${styles}`}>
        {step.status === 'done' ? <Check size={16} strokeWidth={3} /> : step.status === 'error' ? <X size={16} strokeWidth={3} /> : index + 1}
      </span>
      <div className="pt-1">
        <p className={`font-medium ${step.status === 'pending' ? 'text-haze' : 'text-parchment'}`}>{step.name}</p>
        <p className="text-xs text-haze">
          {step.status === 'running' && <span className="text-arcane-300">en cours…</span>}
          {step.status === 'done' && step.duration !== undefined && formatDuration(step.duration * 1000)}
        </p>
      </div>
    </li>
  )
}

export function Timeline({ steps }: { steps: StepState[] }) {
  const done = steps.filter((s) => s.status === 'done').length
  if (!steps.length) return <p className="text-sm text-haze">{texts.run.noSteps}</p>
  return (
    <ol className="relative" aria-label={`${texts.run.steps} : ${done} sur ${steps.length} terminées`}>
      <span aria-hidden="true" className="absolute left-[15px] top-2 bottom-2 w-0.5 bg-line-strong" />
      <span
        aria-hidden="true"
        className="absolute left-[15px] top-2 w-0.5 bg-gradient-to-b from-gold-300 to-arcane-400 transition-[height] duration-[var(--duration-slow)] ease-[var(--ease-out-magic)]"
        style={{ height: `calc((100% - 1rem) * ${steps.length > 1 ? Math.min(done, steps.length - 1) / (steps.length - 1) : 0})` }}
      />
      {steps.map((step, i) => <StepNode key={step.name} step={step} index={i} />)}
    </ol>
  )
}
