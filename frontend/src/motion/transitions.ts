/**
 * Éléments partagés entre pages (GSAP Flip).
 * Avant de quitter une page, on photographie tous les éléments [data-flip-id] ;
 * la page suivante rejoue l'animation depuis cette photo vers les éléments de même identifiant.
 */
import { Flip, gsap } from './gsap'
import { d, ease } from './tokens'

let pending: Flip.FlipState | null = null

export function captureShared() {
  const elements = document.querySelectorAll<HTMLElement>('[data-flip-id]')
  pending = elements.length ? Flip.getState(elements, { props: 'opacity,color' }) : null
}

export function playShared() {
  if (!pending) return
  const state = pending
  pending = null
  const targets = document.querySelectorAll<HTMLElement>('[data-flip-id]')
  if (!targets.length) return
  Flip.from(state, {
    targets,
    duration: d('slow'),
    ease: ease.inOut,
    absolute: true,
    scale: true,
    prune: true,
    zIndex: 60,
    onEnter: (els) => gsap.fromTo(els, { opacity: 0 }, { opacity: 1, duration: d('base') }),
  })
}
