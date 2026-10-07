/** Lueur qui suit le curseur (souris uniquement, jamais en mouvement réduit). Le curseur natif reste : on ne cache rien. */
import { useEffect, useRef } from 'react'
import { gsap } from '../../motion/gsap'
import { useFinePointer, useReducedMotion } from '../../motion/useReducedMotion'

export function CursorGlow() {
  const ref = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion()
  const fine = useFinePointer()

  useEffect(() => {
    const el = ref.current
    if (!el || reduced || !fine) return
    const x = gsap.quickTo(el, 'x', { duration: 0.6, ease: 'power3.out' })
    const y = gsap.quickTo(el, 'y', { duration: 0.6, ease: 'power3.out' })
    const move = (e: PointerEvent) => {
      x(e.clientX)
      y(e.clientY)
      el.style.opacity = '1'
    }
    const hide = () => (el.style.opacity = '0')
    window.addEventListener('pointermove', move, { passive: true })
    document.addEventListener('pointerleave', hide)
    return () => {
      window.removeEventListener('pointermove', move)
      document.removeEventListener('pointerleave', hide)
    }
  }, [reduced, fine])

  if (reduced || !fine) return null
  return (
    <div
      ref={ref}
      aria-hidden="true"
      className="pointer-events-none fixed left-0 top-0 z-0 -ml-[260px] -mt-[260px] size-[520px] rounded-full opacity-0 transition-opacity duration-700 mix-blend-screen"
      style={{ background: 'radial-gradient(circle, rgba(102,132,168,0.10), rgba(134,191,174,0.04) 40%, transparent 65%)' }}
    />
  )
}
