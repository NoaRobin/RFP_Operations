/** Défilement fluide Lenis, synchronisé avec le ticker GSAP et ScrollTrigger. Coupé en mouvement réduit. */
import { useEffect } from 'react'
import Lenis from 'lenis'
import { gsap, ScrollTrigger } from '../../motion/gsap'
import { useReducedMotion } from '../../motion/useReducedMotion'

let instance: Lenis | null = null

export function scrollToTop() {
  if (instance) instance.scrollTo(0, { immediate: true })
  else window.scrollTo(0, 0)
}

export function SmoothScroll() {
  const reduced = useReducedMotion()
  useEffect(() => {
    if (reduced) return
    const lenis = new Lenis({ duration: 1.1, easing: (t) => 1 - Math.pow(1 - t, 4), smoothWheel: true })
    instance = lenis
    lenis.on('scroll', ScrollTrigger.update)
    const tick = (time: number) => lenis.raf(time * 1000)
    gsap.ticker.add(tick)
    gsap.ticker.lagSmoothing(0)
    return () => {
      gsap.ticker.remove(tick)
      lenis.destroy()
      instance = null
    }
  }, [reduced])
  return null
}
