/**
 * Vocabulaire de mouvement de MERLIN.
 * Mêmes courbes et mêmes durées partout : un composant ne définit jamais sa propre courbe.
 * Miroir CSS : --ease-* et --duration-* dans src/styles/tokens.css.
 */
import { gsap } from 'gsap'

export const ease = {
  /** Entrées : décélération longue, « ça se pose ». */
  out: 'expo.out',
  /** Sorties : accélération franche. */
  in: 'power3.in',
  /** Transitions de page, déplacements partagés. */
  inOut: 'power3.inOut',
  /** Micro-interactions joyeuses (boutons, étoiles). */
  spring: 'back.out(1.7)',
  /** Respirations, lueurs. */
  breathe: 'sine.inOut',
} as const

export const duration = {
  instant: 0.12,
  fast: 0.25,
  base: 0.45,
  slow: 0.8,
  epic: 1.4,
} as const

export const stagger = {
  tight: 0.025,
  base: 0.06,
  loose: 0.12,
} as const

/** Distances standard (px) */
export const distance = {
  nudge: 4,
  lift: 12,
  enter: 24,
  fall: 40,
} as const

export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** Durée effective : en mouvement réduit, les animations restent (fondus) mais deviennent quasi instantanées. */
export function d(key: keyof typeof duration): number {
  return prefersReducedMotion() ? Math.min(duration[key], 0.15) : duration[key]
}

/** Distance effective : nulle en mouvement réduit (pas de déplacement, seulement de l'opacité). */
export function dist(key: keyof typeof distance): number {
  return prefersReducedMotion() ? 0 : distance[key]
}

gsap.defaults({ ease: ease.out, duration: duration.base })
