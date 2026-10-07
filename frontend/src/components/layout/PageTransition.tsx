/**
 * Transitions de page orchestrées par GSAP :
 * 1. photo des éléments partagés (Flip), 2. sortie de la page (fondu + flou + voile),
 * 3. changement de route, 4. entrée de la page + vol des éléments partagés.
 * Les liens restent de vrais <a> : clavier, clic molette et lecteurs d'écran fonctionnent normalement.
 */
import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { useLocation, type Location } from 'react-router-dom'
import { gsap, ScrollTrigger } from '../../motion/gsap'
import { d, dist, ease } from '../../motion/tokens'
import { captureShared, playShared } from '../../motion/transitions'
import { scrollToTop } from '../fx/SmoothScroll'

export function PageTransition({ children }: { children: (location: Location) => ReactNode }) {
  const location = useLocation()
  const [display, setDisplay] = useState(location)
  const container = useRef<HTMLDivElement>(null)
  const veil = useRef<HTMLDivElement>(null)
  const first = useRef(true)

  // Sortie
  useLayoutEffect(() => {
    if (location.pathname === display.pathname && location.search === display.search) {
      if (location.key !== display.key) setDisplay(location)
      return
    }
    captureShared()
    const tl = gsap.timeline({
      onComplete: () => {
        scrollToTop()
        setDisplay(location)
      },
    })
    tl.to(container.current, { opacity: 0, y: -dist('lift'), filter: 'blur(6px)', duration: d('fast'), ease: ease.in }, 0)
    tl.fromTo(veil.current, { scaleY: 0, transformOrigin: '50% 100%' }, { scaleY: 1, duration: d('fast'), ease: ease.in }, 0)
    return () => {
      tl.kill()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location])

  // Entrée
  useLayoutEffect(() => {
    if (first.current) {
      first.current = false
      gsap.fromTo(container.current, { opacity: 0 }, { opacity: 1, duration: d('slow') })
      return
    }
    const tl = gsap.timeline()
    tl.set(veil.current, { transformOrigin: '50% 0%' })
    tl.to(veil.current, { scaleY: 0, duration: d('base'), ease: ease.inOut }, 0)
    tl.fromTo(container.current, { opacity: 0, y: dist('enter'), filter: 'blur(6px)' }, { opacity: 1, y: 0, filter: 'blur(0px)', duration: d('slow'), ease: ease.out, clearProps: 'filter,transform' }, 0.05)
    playShared()
    document.getElementById('contenu')?.focus({ preventScroll: true })
    requestAnimationFrame(() => ScrollTrigger.refresh())
  }, [display])

  return (
    <>
      <div ref={container}>{children(display)}</div>
      <div
        ref={veil}
        aria-hidden="true"
        className="pointer-events-none fixed inset-0 z-[70] origin-bottom scale-y-0"
        style={{ background: 'linear-gradient(180deg, rgba(91,33,182,0.18), rgba(7,6,15,0.92) 40%, rgba(7,6,15,0.98))' }}
      />
    </>
  )
}
