/** 404 : un nœud de données s'est détaché de sa constellation. Le bouton de retour reste évident. */
import { useRef } from 'react'
import { ArrowLeft } from 'lucide-react'
import { ButtonLink } from '../components/ui/Button'
import { texts } from '../content/texts'
import { gsap, useGSAP } from '../motion/gsap'
import { d, ease, prefersReducedMotion } from '../motion/tokens'

const NODES = [[60, 70], [95, 52], [130, 66], [118, 104], [80, 110], [100, 82]]
const LINKS = [[0, 1], [1, 2], [2, 3], [3, 4], [4, 0], [5, 0], [5, 2], [5, 4]]

export default function NotFound() {
  const root = useRef<HTMLDivElement>(null)
  useGSAP(
    () => {
      gsap.from('[data-enter]', { opacity: 0, y: 24, stagger: 0.1, duration: d('slow'), ease: ease.out })
      if (prefersReducedMotion()) return
      gsap.to('[data-lost]', { x: 26, y: -18, duration: 2.4, yoyo: true, repeat: -1, ease: ease.breathe })
      gsap.to('[data-tether]', { strokeDashoffset: -20, duration: 1.2, repeat: -1, ease: 'none' })
      gsap.to('[data-ring]', { rotate: 360, transformOrigin: '100px 85px', duration: 40, repeat: -1, ease: 'none' })
    },
    { scope: root },
  )

  return (
    <div ref={root} className="mx-auto flex min-h-[70vh] w-[min(100%-2rem,48rem)] flex-col items-center justify-center pt-12 text-center">
      <svg data-enter viewBox="0 0 220 170" className="w-64" role="img" aria-label="Une constellation dont un point s'est égaré">
        <ellipse data-ring cx="100" cy="85" rx="70" ry="22" fill="none" stroke="#cdb07a" strokeOpacity="0.35" strokeWidth="0.8" />
        {LINKS.map(([a, b]) => (
          <line key={`${a}-${b}`} x1={NODES[a][0]} y1={NODES[a][1]} x2={NODES[b][0]} y2={NODES[b][1]} stroke="#8fa6c3" strokeOpacity="0.45" strokeWidth="0.8" />
        ))}
        {NODES.map(([x, y], i) => <circle key={i} cx={x} cy={y} r={i === 5 ? 4 : 3} fill={i === 5 ? '#e3cfa1' : '#b7c6da'} />)}
        <g data-lost>
          <line data-tether x1="130" y1="66" x2="176" y2="40" stroke="#e3cfa1" strokeOpacity="0.5" strokeDasharray="3 4" strokeWidth="0.8" />
          <circle cx="176" cy="40" r="5" fill="none" stroke="#e3cfa1" strokeWidth="1.2" />
          <text x="186" y="34" fill="#e3cfa1" fontSize="14" fontFamily="Instrument Serif, Georgia, serif">?</text>
        </g>
      </svg>
      <p data-enter className="mt-8 font-mono text-xs uppercase tracking-[0.25em] text-champagne-300">{texts.errors.notFoundCode}</p>
      <h1 data-enter className="mt-4 text-[clamp(2.5rem,6vw,4.25rem)] leading-none">{texts.errors.notFoundTitle}</h1>
      <p data-enter className="mt-4 max-w-lg text-lg text-mist">{texts.errors.notFoundBody}</p>
      <div data-enter className="mt-8">
        <ButtonLink to="/" variant="primary" size="lg" icon={<ArrowLeft size={18} />}>{texts.errors.notFoundCta}</ButtonLink>
      </div>
    </div>
  )
}
