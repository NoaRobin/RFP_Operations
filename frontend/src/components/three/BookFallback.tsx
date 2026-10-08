/** Repli 2D du livre vivant : même livre cartoon en SVG, mêmes humeurs, animé au GSAP, aucune dépendance 3D. */
import { useEffect, useRef } from 'react'
import { gsap } from '../../motion/gsap'
import { d, ease } from '../../motion/tokens'
import type { Mood } from './moods'

const INK = '#1b1530'
const STAR = 'M0 -14 L4.1 -5.6 13.3 -4.3 6.7 2.1 8.2 11.3 0 7 -8.2 11.3 -6.7 2.1 -13.3 -4.3 -4.1 -5.6Z'

export default function BookFallback({ mood, reduced, onPoke, burstKey }: { mood: Mood; reduced: boolean; onPoke?: () => void; burstKey: number }) {
  const root = useRef<SVGSVGElement>(null)
  const book = useRef<SVGGElement>(null)
  const cover = useRef<SVGGElement>(null)
  const lids = useRef<SVGRectElement[]>([])
  const pupils = useRef<SVGCircleElement[]>([])
  const stars = useRef<SVGGElement[]>([])

  // Respiration + étoiles en orbite (hors mouvement réduit)
  useEffect(() => {
    if (reduced) return
    const ctx = gsap.context(() => {
      gsap.to(book.current, { y: -8, duration: 1.6, yoyo: true, repeat: -1, ease: ease.breathe })
      stars.current.forEach((s, i) => {
        gsap.to(s, { rotate: 360, transformOrigin: '50% 50%', duration: 6 + i, repeat: -1, ease: 'none' })
        gsap.to(s, { y: i % 2 ? -10 : 10, duration: 1.8 + i * 0.3, yoyo: true, repeat: -1, ease: ease.breathe })
      })
      const blink = () => {
        gsap.timeline({ onComplete: () => void gsap.delayedCall(2.5 + Math.random() * 3, blink) })
          .to(lids.current, { attr: { height: 30 }, duration: 0.08 })
          .to(lids.current, { attr: { height: 0 }, duration: 0.12 })
      }
      gsap.delayedCall(2, blink)
    }, root)
    return () => ctx.revert()
  }, [reduced])

  // Humeur
  useEffect(() => {
    const open = mood === 'focus' ? 0.55 : mood === 'success' ? 0.45 : mood === 'failure' ? 1 : mood === 'awaken' ? 0.82 : 0.9
    gsap.to(cover.current, { scaleX: open, transformOrigin: '0% 50%', duration: d('slow'), ease: ease.spring })
    gsap.to(book.current, {
      rotate: mood === 'failure' ? -8 : 0, filter: mood === 'failure' ? 'grayscale(0.85)' : 'none',
      transformOrigin: '50% 100%', duration: d('slow'), ease: ease.out,
    })
    gsap.to(lids.current, { attr: { height: mood === 'failure' ? 16 : mood === 'focus' ? 7 : 0 }, duration: d('base') })
    gsap.to(pupils.current, { attr: { cy: mood === 'failure' ? 6 : 0 }, duration: d('base') })
  }, [mood])

  // Jaillissement d'étoiles
  useEffect(() => {
    if (!burstKey && mood !== 'success') return
    stars.current.forEach((s, i) => {
      const a = (i / stars.current.length) * Math.PI * 2
      gsap.fromTo(s, { x: 0, scale: 1 }, { x: reduced ? 0 : Math.cos(a) * 40, scale: 1.6, duration: 0.35, yoyo: true, repeat: 1, ease: ease.spring })
    })
    if (book.current && !reduced) gsap.fromTo(book.current, { scaleY: 0.86, scaleX: 1.08 }, { scaleY: 1, scaleX: 1, duration: 0.7, ease: 'elastic.out(1, 0.35)', transformOrigin: '50% 100%' })
  }, [burstKey, mood, reduced])

  // Les yeux suivent le curseur
  useEffect(() => {
    if (reduced) return
    const move = (e: PointerEvent) => {
      const x = (e.clientX / window.innerWidth - 0.5) * 10
      const y = (e.clientY / window.innerHeight - 0.5) * 8
      gsap.to(pupils.current, { attr: { cx: x }, y, duration: 0.3, overwrite: 'auto' })
    }
    window.addEventListener('pointermove', move, { passive: true })
    return () => window.removeEventListener('pointermove', move)
  }, [reduced])

  const colors = ['#ffd23f', '#ff6b9a', '#2ec4b6', '#ffd23f', '#9b82ff']
  const spots = [[30, 50], [205, 40], [222, 150], [22, 160], [120, 18]]
  return (
    <div className="absolute inset-0 grid place-items-center" aria-hidden="true">
      <svg ref={root} viewBox="0 0 250 220" className={`w-[min(80%,24rem)] overflow-visible ${onPoke ? 'cursor-pointer' : ''}`} onClick={onPoke}>
        {spots.map(([x, y], i) => (
          <g key={i} transform={`translate(${x} ${y})`}>
            <g ref={(g) => { if (g) stars.current[i] = g }}>
              <path d={STAR} fill={colors[i]} stroke={INK} strokeWidth="3" strokeLinejoin="round" />
            </g>
          </g>
        ))}
        <g ref={book}>
          <ellipse cx="125" cy="205" rx="70" ry="8" fill={INK} opacity=".15" />
          {/* dos + pages */}
          <rect x="62" y="40" width="130" height="156" rx="10" fill="#6a4bea" stroke={INK} strokeWidth="4" />
          <rect x="70" y="46" width="118" height="144" rx="6" fill="#fffaf0" stroke={INK} strokeWidth="3" />
          {[70, 84, 98, 112].map((y) => <rect key={y} x="120" y={y} width="56" height="5" rx="2.5" fill="#c9c2dc" />)}
          {/* couverture articulée à gauche */}
          <g ref={cover} transform="translate(62 0)">
            <g transform="translate(-62 0)">
              <rect x="62" y="36" width="124" height="160" rx="12" fill="#7c5cff" stroke={INK} strokeWidth="4" />
              {[-1, 1].map((side, i) => (
                <g key={side} transform={`translate(${124 + side * 24} 92)`}>
                  <ellipse rx="17" ry="21" fill="#fff" stroke={INK} strokeWidth="3.5" />
                  <circle ref={(c) => { if (c) pupils.current[i] = c }} r="7.5" fill={INK} />
                  <clipPath id={`lid-${i}`}><ellipse rx="15.5" ry="19.5" /></clipPath>
                  <rect ref={(r) => { if (r) lids.current[i] = r }} x="-18" y="-20" width="36" height="0" fill="#6a4bea" clipPath={`url(#lid-${i})`} />
                </g>
              ))}
              <path d="M110 128 q14 12 28 0" fill="none" stroke={INK} strokeWidth="3.5" strokeLinecap="round" />
              <g transform="translate(124 162) scale(1.1)"><path d={STAR} fill="#ffd23f" stroke={INK} strokeWidth="3" strokeLinejoin="round" /></g>
            </g>
          </g>
        </g>
      </svg>
    </div>
  )
}
