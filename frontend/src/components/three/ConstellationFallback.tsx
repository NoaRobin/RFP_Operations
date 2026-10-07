/** Repli 2D de la constellation : un globe à méridiens en SVG, mêmes humeurs, aucune dépendance 3D. */
import { useEffect, useMemo, useRef } from 'react'
import { gsap } from '../../motion/gsap'
import { d, ease } from '../../motion/tokens'
import { MOODS, type Mood } from './moods'

export default function ConstellationFallback({ mood, reduced, onPoke, burstKey }: { mood: Mood; reduced: boolean; onPoke?: () => void; burstKey: number }) {
  const m = MOODS[mood]
  const globe = useRef<SVGGElement>(null)
  const wave = useRef<SVGCircleElement>(null)
  const dots = useMemo(
    () => Array.from({ length: 70 }, (_, i) => {
      const golden = Math.PI * (3 - Math.sqrt(5))
      const y = 1 - (i / 69) * 2
      const r = Math.sqrt(1 - y * y)
      return { x: 100 + Math.cos(golden * i) * r * 70, y: 100 + y * 70, z: Math.sin(golden * i) * r }
    }),
    [],
  )

  useEffect(() => {
    if (!globe.current) return
    gsap.to(globe.current, {
      rotate: m.fall * 14, y: m.fall * 10, scale: m.scale, transformOrigin: '50% 50%',
      filter: mood === 'failure' ? 'grayscale(0.9) brightness(0.65)' : 'none', duration: d('slow'), ease: ease.out,
    })
  }, [mood, m.fall, m.scale])

  useEffect(() => {
    if ((!burstKey && mood !== 'success') || !wave.current) return
    gsap.fromTo(wave.current, { attr: { r: 10 }, opacity: 0.9 }, { attr: { r: 98 }, opacity: 0, duration: reduced ? 0.3 : 1.4, ease: 'power2.out' })
  }, [burstKey, mood, reduced])

  const spin = reduced ? undefined : { animation: `spin ${Math.max(10, 60 - m.speed * 90)}s linear infinite`, transformOrigin: '100px 100px' }
  return (
    <div className="absolute inset-0 grid place-items-center" aria-hidden="true">
      <div className="absolute size-[60%] max-w-[24rem] aspect-square rounded-full blur-3xl opacity-50" style={{ background: `radial-gradient(circle, ${m.core}44, transparent 65%)` }} />
      <svg viewBox="0 0 200 200" className={`w-[min(80%,26rem)] ${onPoke ? 'cursor-pointer' : ''}`} onClick={onPoke}>
        <g ref={globe}>
          <g style={spin}>
            {[0, 30, 60, 90, 120, 150].map((angle) => (
              <ellipse key={angle} cx="100" cy="100" rx={Math.abs(Math.cos((angle * Math.PI) / 180)) * 78 + 2} ry="78"
                fill="none" stroke="#cdb07a" strokeOpacity={m.ringOpacity * 0.9} strokeWidth="0.5" />
            ))}
          </g>
          <ellipse cx="100" cy="100" rx="86" ry="22" fill="none" stroke={m.core} strokeOpacity={m.ringOpacity} strokeWidth="0.6" />
          {dots.map((p, i) => (
            <circle key={i} cx={p.x} cy={p.y} r={1 + (p.z + 1) * 0.6} fill={m.node} opacity={0.35 + (p.z + 1) * 0.3} />
          ))}
          <circle cx="100" cy="100" r="9" fill={m.core} opacity="0.9" />
          <circle ref={wave} cx="100" cy="100" r="10" fill="none" stroke="#e3cfa1" strokeWidth="1.2" opacity="0" />
        </g>
      </svg>
    </div>
  )
}
