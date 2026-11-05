/**
 * Univers courant : couleur de toute l'app (html[data-universe]) et, au passage d'un univers à l'autre, l'entrée en
 * scène de sa mascotte (Merlin, Gus, Alfred…) le temps de la transition. Mouvement réduit : la couleur change, sans scène.
 */
import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { gsap } from '../motion/gsap'
import { useReducedMotion } from '../motion/useReducedMotion'
import { Mascot } from './Mascots'
import { universeOf, type Universe } from './universes'

export function useUniverse(): Universe {
  return universeOf(useLocation().pathname)
}

export function UniverseLayer() {
  const u = useUniverse()
  const reduced = useReducedMotion()
  const previous = useRef<string | null>(null)
  const [scene, setScene] = useState<Universe | null>(null)
  const card = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const first = previous.current === null
    const changed = previous.current !== u.id
    previous.current = u.id
    if (first || !changed || reduced) {
      document.documentElement.dataset.universe = u.id
      return
    }
    setScene(u)
  }, [u, reduced])

  useEffect(() => {
    if (!scene || !card.current) return
    const el = card.current
    const tl = gsap.timeline({ onComplete: () => setScene(null) })
    tl.fromTo(el, { opacity: 0, scale: 0.6, rotate: -8 }, { opacity: 1, scale: 1, rotate: 0, duration: 0.32, ease: 'back.out(1.8)' })
    tl.call(() => { document.documentElement.dataset.universe = scene.id }, [], 0.18)
    tl.to(el.querySelector('[data-mascot]'), { y: -6, duration: 0.18, yoyo: true, repeat: 1, ease: 'power1.inOut' }, 0.3)
    tl.to(el, { opacity: 0, scale: 0.9, y: -12, duration: 0.24, ease: 'power2.in' }, 0.95)
    return () => { tl.kill(); document.documentElement.dataset.universe = scene.id }
  }, [scene])

  if (!scene) return null
  return (
    <div className="pointer-events-none fixed inset-0 z-[90] grid place-items-center" aria-hidden="true">
      <div ref={card} className="flex items-center gap-4 rounded-[var(--radius-card)] border-[3px] border-fg bg-card px-6 py-4 shadow-[6px_6px_0_0_var(--color-fg)]"
        style={{ borderColor: scene.accent }}>
        <span data-mascot><Mascot universe={scene.id} className="size-20" /></span>
        <span className="flex flex-col">
          <span className="font-display text-3xl font-bold leading-none" style={{ color: scene.accent === '#ffd23f' ? '#6e4300' : scene.accent }}>{scene.name}</span>
          <span className="mt-1 text-sm font-bold text-fg-2">{scene.greeting}</span>
        </span>
      </div>
    </div>
  )
}
