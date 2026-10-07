import { useLayoutEffect, useRef } from 'react'
import { gsap } from '../../motion/gsap'
import { d, ease } from '../../motion/tokens'
import { formatNumber } from '../../lib/format'

/** Chiffre animé. Le texte final est toujours présent pour les lecteurs d'écran. */
export function CountUp({ value, digits = 0, suffix = '', className = '' }: { value: number; digits?: number; suffix?: string; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null)
  const previous = useRef(0)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const counter = { v: previous.current }
    const tween = gsap.to(counter, {
      v: value,
      duration: d('epic'),
      ease: ease.out,
      onUpdate: () => {
        el.textContent = formatNumber(counter.v, digits) + suffix
      },
    })
    previous.current = value
    return () => {
      tween.kill()
    }
  }, [value, digits, suffix])
  return (
    <span className={`tabular-nums ${className}`}>
      <span ref={ref} aria-hidden="true">{formatNumber(0, digits) + suffix}</span>
      <span className="sr-only">{formatNumber(value, digits) + suffix}</span>
    </span>
  )
}
