/**
 * Jauge de liquide verticale : un moteur de recherche, son niveau monte pendant qu'il travaille (GSAP), puis se pose
 * sur sa contribution réelle aux résultats. Vague en surface (désactivée en mouvement réduit).
 */
import { useEffect, useId, useRef } from 'react'
import { gsap } from '../../motion/gsap'
import { useReducedMotion } from '../../motion/useReducedMotion'

export function LiquidGauge({ label, level, color, busy, detail, off }: { label: string; level: number; color: string; busy: boolean; detail?: string; off?: boolean }) {
  const id = useId().replace(/:/g, '')
  const liquid = useRef<SVGGElement>(null)
  const reduced = useReducedMotion()
  const H = 200
  useEffect(() => {
    if (!liquid.current) return
    const target = busy ? 0.55 + Math.random() * 0.3 : off ? 0 : Math.max(0.04, Math.min(1, level))
    const y = H * (1 - target)
    if (reduced) { liquid.current.setAttribute('transform', `translate(0 ${y})`); return }
    const tween = gsap.to(liquid.current, { attr: { transform: `translate(0 ${y})` }, duration: busy ? 1.8 : 1.1, ease: busy ? 'sine.inOut' : 'power2.out' })
    return () => { tween.kill() }
  }, [level, busy, off, reduced])
  const wave = (shift: number) => `M ${-60 + shift} 6 Q ${-45 + shift} 3 ${-30 + shift} 6 T ${0 + shift} 6 T ${30 + shift} 6 T ${60 + shift} 6 T ${90 + shift} 6 T ${120 + shift} 6 V ${H + 20} H ${-60 + shift} Z`
  return (
    <figure className={`flex flex-col items-center gap-2 ${off ? 'opacity-45' : ''}`}>
      <svg viewBox={`0 0 60 ${H + 8}`} className="h-32 w-7" role="img" aria-label={`${label} : ${off ? 'inactif' : `${Math.round(level * 100)} %`}`}>
        <defs>
          <clipPath id={`tube-${id}`}><rect x="8" y="4" width="44" height={H} rx="22" /></clipPath>
          <linearGradient id={`fill-${id}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={color} stopOpacity="0.7" />
            <stop offset="1" stopColor={color} stopOpacity="0.25" />
          </linearGradient>
        </defs>
        <rect x="8" y="4" width="44" height={H} rx="22" fill="#0d1117" stroke="#3d444d" />
        <g clipPath={`url(#tube-${id})`}>
          <g ref={liquid} transform={`translate(0 ${H})`}>
            <path d={wave(0)} fill={`url(#fill-${id})`} className="qv-wave" style={{ animation: 'qv-wave 6s linear infinite' }} />
            <path d={wave(15)} fill={color} opacity="0.18" className="qv-wave" style={{ animation: 'qv-wave 9s linear infinite reverse' }} />
          </g>
        </g>
        {[0.25, 0.5, 0.75].map((t) => <line key={t} x1="44" x2="52" y1={4 + H * t} y2={4 + H * t} stroke="#3d444d" />)}
        <rect x="8" y="4" width="44" height={H} rx="22" fill="none" stroke={color} strokeOpacity="0" />
      </svg>
      <figcaption className="text-center">
        <span className="block text-xs font-semibold text-fg">{label}</span>
        <span className="qv-meter block text-[0.7rem] text-fg-3">{off ? 'inactif' : busy ? '…' : detail ?? `${Math.round(level * 100)} %`}</span>
      </figcaption>
    </figure>
  )
}
