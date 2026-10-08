/**
 * La course-poursuite : des livres paniqués détalent, poursuivis par des appels d'offres (RFI, RFP, DDQ…) furieux.
 * SVG + GSAP. Survol : la course accélère. Clic sur un appel d'offres : il trébuche.
 * Mouvement réduit : une image fixe, aucune boucle.
 */
import { useRef } from 'react'
import { useToast } from '../ui/Toast'
import { texts, pick } from '../../content/texts'
import { gsap, useGSAP } from '../../motion/gsap'
import { prefersReducedMotion } from '../../motion/tokens'

const INK = '#1b1530'
const GROUND = 214

function Legs() {
  return (
    <>
      {[-10, 10].map((x, i) => (
        <g key={x} data-leg={i % 2 ? 'b' : 'a'} transform={`translate(${x} -24)`}>
          <line x1="0" y1="0" x2="0" y2="22" stroke={INK} strokeWidth="5" strokeLinecap="round" />
          <ellipse cx="5" cy="23" rx="8" ry="4.5" fill={INK} />
        </g>
      ))}
    </>
  )
}

function Book({ x, color, bubble }: { x: number; color: string; bubble?: string }) {
  return (
    <g transform={`translate(${x} ${GROUND})`}>
      <g data-bob>
        {[0, 1, 2].map((k) => <circle key={k} data-dust cx={-30 - k * 6} cy={-4} r={7 - k} fill={INK} opacity="0" />)}
        <Legs />
        <g data-arm transform="translate(-26 -60)"><line x1="0" y1="0" x2="-18" y2="-16" stroke={INK} strokeWidth="5" strokeLinecap="round" /></g>
        <g data-arm transform="translate(26 -60)"><line x1="0" y1="0" x2="18" y2="-18" stroke={INK} strokeWidth="5" strokeLinecap="round" /></g>
        <rect x="-28" y="-96" width="56" height="74" rx="7" fill={color} stroke={INK} strokeWidth="4" />
        <rect x="20" y="-91" width="9" height="64" rx="2" fill="#fff" stroke={INK} strokeWidth="3" />
        <line x1="-19" y1="-94" x2="-19" y2="-24" stroke={INK} strokeWidth="2.5" opacity=".35" />
        {/* Yeux affolés qui regardent derrière */}
        <ellipse cx="-9" cy="-72" rx="8" ry="10" fill="#fff" stroke={INK} strokeWidth="3" />
        <ellipse cx="10" cy="-72" rx="8" ry="10" fill="#fff" stroke={INK} strokeWidth="3" />
        <circle cx="-12" cy="-71" r="3.6" fill={INK} />
        <circle cx="7" cy="-71" r="3.6" fill={INK} />
        <ellipse cx="0" cy="-47" rx="5" ry="7" fill={INK} />
        <path data-sweat d="M33 -96 q-6 9 0 12 q6 -3 0 -12z" fill="#7cd3ff" stroke={INK} strokeWidth="2" />
        {bubble && (
          <g transform="translate(-10 -150)">
            <rect x="-6" y="-24" width={bubble.length * 9.5 + 18} height="34" rx="12" fill="#fff" stroke={INK} strokeWidth="3" />
            <path d="M10 10 l6 14 l8 -14" fill="#fff" stroke={INK} strokeWidth="3" strokeLinejoin="round" />
            <path d="M11 8 h12" stroke="#fff" strokeWidth="4" />
            <text x="3" y="-1" fontFamily="Fredoka, sans-serif" fontWeight="700" fontSize="17" fill={INK}>{bubble}</text>
          </g>
        )}
      </g>
    </g>
  )
}

function Tender({ x, label, color, scale = 1, bubble }: { x: number; label: string; color: string; scale?: number; bubble?: string }) {
  return (
    <g transform={`translate(${x} ${GROUND}) scale(${scale})`}>
      <g data-tender style={{ cursor: 'pointer' }}>
        <g data-bob>
          <Legs />
          <g data-arm transform="translate(36 -62)"><line x1="0" y1="0" x2="22" y2="-6" stroke={INK} strokeWidth="5" strokeLinecap="round" /></g>
          <path d="M-34 -112 h52 l18 18 v72 h-70 z" fill="#fff" stroke={INK} strokeWidth="4" strokeLinejoin="round" />
          <path d="M18 -112 v18 h18" fill="#e9e3f5" stroke={INK} strokeWidth="4" strokeLinejoin="round" />
          {/* Sourcils froncés, yeux plissés, sourire carnassier */}
          <path d="M-22 -92 l12 5 M18 -92 l-12 5" stroke={INK} strokeWidth="4" strokeLinecap="round" />
          <circle cx="-12" cy="-80" r="3.5" fill={INK} />
          <circle cx="8" cy="-80" r="3.5" fill={INK} />
          <path d="M-16 -66 q14 10 28 0 z" fill="#fff" stroke={INK} strokeWidth="3" strokeLinejoin="round" />
          <path d="M-9 -66 v4 M-2 -66 v6 M5 -66 v4" stroke={INK} strokeWidth="2" />
          <rect x="-26" y="-52" width={label.length * 13 + 12} height="22" rx="6" fill={color} stroke={INK} strokeWidth="3" />
          <text x="-20" y="-35" fontFamily="Fredoka, sans-serif" fontWeight="700" fontSize="17" fill={INK}>{label}</text>
          {bubble && (
            <g transform="translate(-40 -160)">
              <rect x="-6" y="-24" width={bubble.length * 8.6 + 18} height="34" rx="12" fill="#ffd23f" stroke={INK} strokeWidth="3" />
              <path d="M40 10 l4 16 l10 -16" fill="#ffd23f" stroke={INK} strokeWidth="3" strokeLinejoin="round" />
              <path d="M41 8 h12" stroke="#ffd23f" strokeWidth="4" />
              <text x="3" y="-1" fontFamily="Fredoka, sans-serif" fontWeight="700" fontSize="16" fill={INK}>{bubble}</text>
            </g>
          )}
        </g>
      </g>
    </g>
  )
}

export function Chase({ className = '' }: { className?: string }) {
  const root = useRef<HTMLDivElement>(null)
  const parade = useRef<gsap.core.Tween | null>(null)
  const toast = useToast()

  useGSAP(
    () => {
      if (prefersReducedMotion()) {
        gsap.set('[data-parade]', { x: 120 })
        return
      }
      parade.current = gsap.fromTo('[data-parade]', { x: -1150 }, { x: 1300, duration: 13, ease: 'none', repeat: -1 })
      gsap.utils.toArray<SVGGElement>('[data-bob]').forEach((el, i) => {
        gsap.to(el, { y: -9, duration: 0.17, yoyo: true, repeat: -1, ease: 'power1.out', delay: i * 0.05 })
      })
      gsap.fromTo('[data-leg="a"]', { rotation: -32 }, { rotation: 32, transformOrigin: '50% 0%', duration: 0.17, yoyo: true, repeat: -1, ease: 'sine.inOut' })
      gsap.fromTo('[data-leg="b"]', { rotation: 32 }, { rotation: -32, transformOrigin: '50% 0%', duration: 0.17, yoyo: true, repeat: -1, ease: 'sine.inOut' })
      gsap.fromTo('[data-arm]', { rotation: -25 }, { rotation: 25, transformOrigin: '0% 0%', duration: 0.2, yoyo: true, repeat: -1, ease: 'sine.inOut', stagger: 0.07 })
      gsap.fromTo('[data-sweat]', { y: 0, opacity: 1 }, { y: -14, x: 8, opacity: 0, duration: 0.6, repeat: -1, ease: 'power1.out', stagger: 0.2 })
      gsap.fromTo('[data-dust]', { scale: 0.2, opacity: 0.5, x: 0 }, { scale: 1.6, opacity: 0, x: -24, transformOrigin: '50% 50%', duration: 0.5, repeat: -1, stagger: 0.12, ease: 'power1.out' })
    },
    { scope: root },
  )

  const speed = (factor: number) => {
    if (parade.current) gsap.to(parade.current, { timeScale: factor, duration: 0.4 })
  }

  const trip = (e: React.MouseEvent) => {
    const tender = (e.target as Element).closest('[data-tender]')
    if (!tender) return
    toast('magic', pick(texts.home.chase.tripped))
    if (prefersReducedMotion()) return
    gsap.timeline()
      .to(tender, { rotation: -80, transformOrigin: '50% 100%', y: 6, duration: 0.25, ease: 'power2.in' })
      .to(tender, { rotation: 0, y: 0, duration: 0.6, ease: 'back.out(2)', delay: 0.9 })
  }

  return (
    <div ref={root} className={`relative overflow-hidden rounded-[var(--radius-card)] border-[2.5px] border-fg bg-[#c7ecff] shadow-[var(--shadow-pop)] ${className}`}
      onPointerEnter={() => speed(2.4)} onPointerLeave={() => speed(1)}>
      <svg viewBox="0 0 1200 250" preserveAspectRatio="xMidYMax slice" className="block h-[14rem] w-full sm:h-[17rem]" role="img"
        aria-label="Des livres paniqués s'enfuient, poursuivis par des appels d'offres RFI, RFP et DDQ." onClick={trip}>
        <circle cx="1100" cy="50" r="30" fill="#ffd23f" stroke={INK} strokeWidth="4" />
        <g fill="#fff" stroke={INK} strokeWidth="3">
          <path d="M140 60 a18 18 0 0 1 34 -6 a14 14 0 0 1 22 12 h-60 a10 10 0 0 1 4 -6z" />
          <path d="M620 40 a18 18 0 0 1 34 -6 a14 14 0 0 1 22 12 h-60 a10 10 0 0 1 4 -6z" />
          <path d="M880 80 a14 14 0 0 1 26 -4 a11 11 0 0 1 17 9 h-46 a8 8 0 0 1 3 -5z" />
        </g>
        <rect x="0" y={GROUND} width="1200" height="40" fill="#7ad99a" stroke={INK} strokeWidth="4" />
        {[60, 260, 470, 690, 930, 1130].map((x) => <path key={x} d={`M${x} ${GROUND} l6 -12 l4 12 l6 -9 l3 9`} fill="none" stroke={INK} strokeWidth="3" strokeLinejoin="round" />)}
        <g data-parade>
          <Tender x={60} label="DDQ" color="#9b82ff" scale={1.25} />
          <Tender x={250} label="RFP" color="#ff6b9a" bubble={texts.home.chase.chaser} />
          <Tender x={420} label="RFI" color="#2ec4b6" scale={0.9} />
          <Tender x={540} label="AO" color="#ffd23f" scale={0.75} />
          <Book x={760} color="#7c5cff" />
          <Book x={880} color="#ff6b9a" bubble={texts.home.chase.runner} />
          <Book x={990} color="#2ec4b6" />
        </g>
      </svg>
      <p className="absolute bottom-3 left-4 rounded-full border-2 border-fg bg-card px-3 py-1 text-xs font-bold">{texts.home.chase.title}</p>
      <p className="sr-only">{texts.home.chase.help}</p>
    </div>
  )
}
