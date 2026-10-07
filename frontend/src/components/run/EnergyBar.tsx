import { useEffect, useRef } from 'react'
import { gsap } from '../../motion/gsap'
import { d, ease } from '../../motion/tokens'
import type { RunStatus } from '../../lib/types'

/** Barre de progression « énergie magique » : déterminée si on connaît l'avancement, sinon chatoyante. */
export function EnergyBar({ value, status, label }: { value: number | null; status: RunStatus; label: string }) {
  const fill = useRef<HTMLDivElement>(null)
  const pct = status === 'success' ? 100 : Math.round((value ?? 0) * 100)
  const indeterminate = value === null && (status === 'running' || status === 'queued')

  useEffect(() => {
    if (!fill.current || indeterminate) return
    gsap.to(fill.current, { width: `${Math.max(pct, 3)}%`, duration: d('slow'), ease: ease.out })
  }, [pct, indeterminate])

  const color =
    status === 'error' ? 'from-danger/80 to-danger' : status === 'cancelled' ? 'from-haze to-mist' : 'from-violet-500 via-arcane-400 to-gold-300'

  return (
    <div>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={indeterminate ? undefined : pct}
        aria-valuetext={indeterminate ? 'En cours' : `${pct} %`}
        className="relative h-3 overflow-hidden rounded-full bg-abyss/70 shadow-[inset_0_0_0_1px_var(--color-line-strong)]"
      >
        <div
          ref={fill}
          className={`absolute inset-y-0 left-0 rounded-full bg-gradient-to-r ${color} ${indeterminate ? 'w-full opacity-60' : 'w-[3%]'}`}
        >
          {(status === 'running' || indeterminate) && (
            <span aria-hidden="true" className="absolute inset-0 bg-[linear-gradient(100deg,transparent_20%,rgba(255,255,255,0.55)_50%,transparent_80%)] bg-[length:200%_100%] animate-shimmer" />
          )}
          {status === 'running' && !indeterminate && (
            <span aria-hidden="true" className="absolute right-0 top-1/2 size-4 -translate-y-1/2 translate-x-1/2 rounded-full bg-white shadow-[0_0_18px_6px_rgba(94,234,212,0.8)]" />
          )}
        </div>
      </div>
    </div>
  )
}
