/** Cadran d'instrument : anneau fin lumineux, valeur en chiffres, progression animée par GSAP (instantanée en mouvement réduit). */
import { useEffect, useRef } from 'react'
import { gsap } from '../../motion/gsap'
import { useReducedMotion } from '../../motion/useReducedMotion'

export function Dial({ value, label, hint, display, color = '#3b82f6' }: { value: number | null; label: string; hint?: string; display?: string; color?: string }) {
  const arc = useRef<SVGCircleElement>(null)
  const reduced = useReducedMotion()
  const v = value == null ? 0 : Math.max(0, Math.min(1, value))
  const R = 42
  const C = 2 * Math.PI * R * 0.75 // trois quarts de cercle
  useEffect(() => {
    if (!arc.current) return
    const target = C * (1 - v)
    if (reduced) { arc.current.style.strokeDashoffset = String(target); return }
    gsap.fromTo(arc.current, { strokeDashoffset: C }, { strokeDashoffset: target, duration: 1.4, ease: 'power3.out' })
  }, [v, C, reduced])
  const text = display ?? (value == null ? '—' : `${Math.round(v * 100)} %`)
  return (
    <figure className="flex flex-col items-center text-center">
      <svg viewBox="0 0 100 100" className="w-full max-w-[9.5rem]" role="img" aria-label={`${label} : ${text}`}>
        <g transform="rotate(135 50 50)">
          <circle cx="50" cy="50" r={R} fill="none" stroke="rgb(120 160 255 / 0.14)" strokeWidth="5" strokeDasharray={`${C} 999`} strokeLinecap="round" />
          {value != null && (
            <circle ref={arc} cx="50" cy="50" r={R} fill="none" stroke={color} strokeWidth="5" strokeDasharray={`${C} 999`} strokeDashoffset={C}
              strokeLinecap="round" style={{ filter: `drop-shadow(0 0 6px ${color})` }} />
          )}
        </g>
        <text x="50" y="56" textAnchor="middle" fontSize="17" fontWeight="600" fill="var(--color-fg)" className="qv-meter">{text}</text>
      </svg>
      <figcaption className="-mt-2 font-display text-sm font-semibold">{label}</figcaption>
      {hint && <p className="mt-0.5 max-w-[14rem] text-xs text-fg-3">{hint}</p>}
    </figure>
  )
}
