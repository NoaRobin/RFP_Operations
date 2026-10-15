import { useEffect, useRef } from 'react'
import { gsap } from '../../motion/gsap'
import { d, ease } from '../../motion/tokens'
import { useFinePointer, useReducedMotion } from '../../motion/useReducedMotion'

/**
 * Profondeur au survol : inclinaison 3D légère + halo (variables CSS --mx/--my/--halo-o, cf. .halo).
 * Désactivé au doigt et en mouvement réduit (le halo reste, l'inclinaison non).
 */
export function useTilt<T extends HTMLElement>(max = 6) {
  const ref = useRef<T>(null)
  const reduced = useReducedMotion()
  const fine = useFinePointer()

  useEffect(() => {
    const el = ref.current
    if (!el || !fine) return
    const rx = gsap.quickTo(el, 'rotationX', { duration: d('slow'), ease: ease.out })
    const ry = gsap.quickTo(el, 'rotationY', { duration: d('slow'), ease: ease.out })
    gsap.set(el, { transformPerspective: 900, transformStyle: 'preserve-3d' })

    const move = (e: PointerEvent) => {
      const rect = el.getBoundingClientRect()
      const px = (e.clientX - rect.left) / rect.width
      const py = (e.clientY - rect.top) / rect.height
      el.style.setProperty('--mx', `${px * 100}%`)
      el.style.setProperty('--my', `${py * 100}%`)
      el.style.setProperty('--halo-o', '1')
      if (!reduced) {
        rx((0.5 - py) * max * 2)
        ry((px - 0.5) * max * 2)
      }
    }
    const leave = () => {
      el.style.setProperty('--halo-o', '0')
      rx(0)
      ry(0)
    }
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerleave', leave)
    return () => {
      el.removeEventListener('pointermove', move)
      el.removeEventListener('pointerleave', leave)
    }
  }, [fine, reduced, max])

  return ref
}
