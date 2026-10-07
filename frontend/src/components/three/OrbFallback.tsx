/** Repli 2D du cristal : CSS + SVG, aucune dépendance 3D. Même vocabulaire d'humeurs. */
import { useEffect, useRef } from 'react'
import { gsap } from '../../motion/gsap'
import { d, ease } from '../../motion/tokens'
import { MOODS, type Mood } from './moods'

export default function OrbFallback({ mood, reduced, onPoke, burstKey }: { mood: Mood; reduced: boolean; onPoke?: () => void; burstKey: number }) {
  const root = useRef<HTMLDivElement>(null)
  const crystal = useRef<HTMLDivElement>(null)
  const sparks = useRef<HTMLDivElement>(null)
  const m = MOODS[mood]

  useEffect(() => {
    const el = crystal.current
    if (!el) return
    gsap.to(el, {
      rotate: m.droop * 40,
      y: m.droop * 30,
      filter: mood === 'failure' ? 'grayscale(0.85) brightness(0.6)' : 'grayscale(0) brightness(1)',
      duration: d('slow'),
      ease: ease.out,
    })
  }, [mood, m.droop])

  useEffect(() => {
    if (!burstKey || reduced || !sparks.current) return
    const dots = Array.from(sparks.current.children) as HTMLElement[]
    dots.forEach((dot, i) => {
      const angle = (i / dots.length) * Math.PI * 2
      gsap.fromTo(dot, { x: 0, y: 0, opacity: 1, scale: 1 }, {
        x: Math.cos(angle) * (90 + Math.random() * 60), y: Math.sin(angle) * (90 + Math.random() * 60) + 40,
        opacity: 0, scale: 0.4, duration: 1.4, ease: 'power2.out',
      })
    })
  }, [burstKey, reduced])

  const spin = reduced ? 'none' : `spin ${Math.max(4, 22 - m.speed * 16)}s linear infinite`
  return (
    <div ref={root} className="absolute inset-0 grid place-items-center" aria-hidden="true">
      <div
        className="absolute size-[70%] max-w-[26rem] max-h-[26rem] aspect-square rounded-full blur-3xl transition-[background,opacity] duration-[var(--duration-slow)]"
        style={{ background: `radial-gradient(circle, ${m.colorA}55, ${m.colorB}22 45%, transparent 70%)`, opacity: 0.4 + m.glow * 0.35 }}
      />
      <div
        className="absolute size-[58%] max-w-[22rem] max-h-[22rem] aspect-square rounded-full border border-dashed"
        style={{ borderColor: `${m.colorB}66`, animation: spin }}
      />
      <div ref={crystal} onClick={onPoke} className={onPoke ? 'cursor-pointer' : ''}>
        <svg viewBox="0 0 100 150" className="w-28 sm:w-36 drop-shadow-[0_0_30px_rgba(167,139,250,0.55)]">
          <defs>
            <linearGradient id="fb-crystal" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor={m.colorA} stopOpacity="0.95" />
              <stop offset="0.55" stopColor="#3b2a7a" />
              <stop offset="1" stopColor={m.colorB} stopOpacity="0.85" />
            </linearGradient>
          </defs>
          <path d="M50 4 L92 72 L50 146 L8 72 Z" fill="url(#fb-crystal)" stroke="#f5dfa5" strokeOpacity="0.7" strokeWidth="1.2" />
          <path d="M8 72 L92 72 M50 4 L50 146 M50 4 L30 72 L50 146 L70 72 Z" fill="none" stroke="#f5dfa5" strokeOpacity="0.35" strokeWidth="0.8" />
          <circle cx="50" cy="72" r={8 + m.glow * 5} fill={m.colorA} opacity="0.85" />
        </svg>
      </div>
      <div ref={sparks} className="absolute">
        {Array.from({ length: 18 }, (_, i) => (
          <span key={i} className="absolute size-1.5 rounded-full opacity-0" style={{ background: i % 3 === 0 ? '#f5dfa5' : i % 3 === 1 ? '#a78bfa' : '#5eead4' }} />
        ))}
      </div>
    </div>
  )
}
