/**
 * Mathilde à sa fenêtre : accoudée, le menton dans les mains, elle regarde passer les nuages… et les RFP en avion de papier.
 * Ses yeux suivent l'avion, elle cligne, soupire, et répond quand on clique (Céline Dion et Koh-Lanta inclus).
 * SVG + GSAP ; en mouvement réduit, scène fixe (les citations changent toujours au clic).
 */
import { useEffect, useRef, useState } from 'react'
import { texts } from '../../content/texts'
import { gsap, useGSAP } from '../../motion/gsap'
import { prefersReducedMotion } from '../../motion/tokens'

const INK = '#1b1530'
const SKIN = '#ffd2b0'
const HAIR = '#6b3a2a'

export function Mathilde({ className = '' }: { className?: string }) {
  const root = useRef<HTMLDivElement>(null)
  const pupils = useRef<SVGGElement>(null)
  const [quote, setQuote] = useState(0)
  const quotes = texts.home.mathilde.quotes

  useGSAP(
    () => {
      gsap.set('[data-lid]', { scaleY: 0, transformOrigin: '50% 0%' })
      if (prefersReducedMotion()) return
      // Nuages et oiseaux qui passent
      gsap.utils.toArray<SVGGElement>('[data-cloud]').forEach((c, i) => {
        gsap.fromTo(c, { x: -140 }, { x: 560, duration: 26 + i * 9, repeat: -1, ease: 'none', delay: -i * 11 })
      })
      gsap.fromTo('[data-birds]', { x: 460 }, { x: -120, duration: 14, repeat: -1, ease: 'none', delay: 3 })
      gsap.to('[data-wing]', { scaleY: -1, transformOrigin: '50% 100%', duration: 0.25, yoyo: true, repeat: -1, ease: 'sine.inOut' })
      // L'avion de papier « RFP » : les yeux de Mathilde le suivent
      const plane = { x: -80 }
      gsap.timeline({ repeat: -1, repeatDelay: 2.5, delay: 1 })
        .fromTo(plane, { x: -80 }, {
          x: 480, duration: 6.5, ease: 'none',
          onUpdate: () => {
            gsap.set('[data-plane]', { x: plane.x, y: Math.sin(plane.x / 45) * 10, rotation: Math.cos(plane.x / 45) * 10 })
            const dx = gsap.utils.clamp(-4.5, 4.5, gsap.utils.mapRange(-80, 480, -4.5, 4.5, plane.x))
            gsap.set(pupils.current, { x: dx, y: -3 })
          },
        })
        .to(pupils.current, { x: 0, y: 0, duration: 0.6, ease: 'power2.out' })
        .fromTo('[data-sigh]', { opacity: 0, scale: 0.4, x: 0, y: 0 }, { opacity: 1, scale: 1, x: 14, y: -10, transformOrigin: '0% 100%', duration: 0.5, ease: 'back.out(2)' }, '<')
        .to('[data-sigh]', { opacity: 0, y: -24, duration: 0.6, delay: 0.8 })
      // Tête qui penche, rideaux qui ondulent, clignements
      gsap.to('[data-head]', { rotation: 4, transformOrigin: '50% 95%', duration: 2.6, yoyo: true, repeat: -1, ease: 'sine.inOut' })
      gsap.to('[data-curtain]', { skewX: 4, transformOrigin: '50% 0%', duration: 2.2, yoyo: true, repeat: -1, ease: 'sine.inOut', stagger: 0.5 })
      gsap.to('[data-cactus]', { rotation: -3, transformOrigin: '50% 100%', duration: 1.8, yoyo: true, repeat: -1, ease: 'sine.inOut' })
      const blink = () => {
        gsap.timeline({ onComplete: () => void gsap.delayedCall(2.5 + Math.random() * 3, blink) })
          .to('[data-lid]', { scaleY: 1, duration: 0.07 })
          .to('[data-lid]', { scaleY: 0, duration: 0.1 })
      }
      gsap.delayedCall(1.5, blink)
    },
    { scope: root },
  )

  // Une nouvelle pensée toutes les 7 secondes
  useEffect(() => {
    const id = window.setInterval(() => setQuote((q) => (q + 1) % quotes.length), 7000)
    return () => window.clearInterval(id)
  }, [quotes.length])

  useEffect(() => {
    if (prefersReducedMotion() || !root.current) return
    gsap.fromTo(root.current.querySelector('[data-bubble]'), { scale: 0.7, rotation: -4, opacity: 0 }, { scale: 1, rotation: 0, opacity: 1, duration: 0.5, ease: 'back.out(2.2)' })
  }, [quote])

  const poke = () => {
    setQuote((q) => (q + 1) % quotes.length)
    if (prefersReducedMotion() || !root.current) return
    gsap.fromTo(root.current.querySelectorAll('[data-heart]'), { y: 0, opacity: 1, scale: 0.4 }, { y: -70, opacity: 0, scale: 1.2, duration: 1.2, stagger: 0.12, ease: 'power1.out' })
    gsap.fromTo('[data-mouth]', { scaleY: 1 }, { scaleY: 2.2, transformOrigin: '50% 0%', duration: 0.15, yoyo: true, repeat: 3 })
  }

  return (
    <div ref={root} className={`relative ${className}`}>
      <p data-bubble role="status" aria-live="polite"
        className="relative z-10 mx-auto mb-4 max-w-sm rounded-3xl border-[2.5px] border-fg bg-card px-5 py-3 text-center font-display text-lg font-semibold shadow-[4px_4px_0_0_var(--color-fg)] after:absolute after:-bottom-[13px] after:left-1/2 after:size-5 after:-translate-x-1/2 after:rotate-45 after:border-b-[2.5px] after:border-r-[2.5px] after:border-fg after:bg-card">
        « {quotes[quote]} »
      </p>
      <svg viewBox="0 0 400 360" className="block w-full overflow-hidden rounded-[var(--radius-card)] border-[2.5px] border-fg shadow-[var(--shadow-pop)]" role="img" aria-label={texts.home.mathilde.label}>
        <defs><clipPath id="m-scene"><rect width="400" height="360" /></clipPath></defs>
        <g clipPath="url(#m-scene)">
          {/* Ciel */}
          <rect width="400" height="360" fill="#c7ecff" />
          <circle cx="340" cy="52" r="26" fill="#ffd23f" stroke={INK} strokeWidth="4" />
          {[30, 70].map((y, i) => (
            <g key={y} data-cloud transform={`translate(0 ${y})`}>
              <path d={`M20 ${10 + i * 4} a16 16 0 0 1 30 -6 a13 13 0 0 1 22 10 h-56 a9 9 0 0 1 4 -4z`} fill="#fff" stroke={INK} strokeWidth="3" />
            </g>
          ))}
          <g data-birds transform="translate(0 40)">
            {[0, 26].map((x) => (
              <g key={x} transform={`translate(${x} ${x / 3})`}>
                <path data-wing d="M0 0 q6 -7 12 0 q6 -7 12 0" fill="none" stroke={INK} strokeWidth="3" strokeLinecap="round" />
              </g>
            ))}
          </g>
          <g data-plane transform="translate(-80 0)">
            <g transform="translate(0 88)">
              <path d="M0 0 L46 -12 L12 8 Z" fill="#fff" stroke={INK} strokeWidth="3" strokeLinejoin="round" />
              <path d="M12 8 L18 -4 L46 -12" fill="#e9e3f5" stroke={INK} strokeWidth="3" strokeLinejoin="round" />
              <path d="M-4 2 q-14 -6 -24 0" fill="none" stroke={INK} strokeWidth="2" strokeDasharray="3 4" />
              <rect x="-62" y="-6" width="40" height="18" rx="5" fill="#ff6b9a" stroke={INK} strokeWidth="2.5" />
              <text x="-56" y="8" fontFamily="Fredoka, sans-serif" fontWeight="700" fontSize="13" fill={INK}>RFP</text>
            </g>
          </g>

          {/* Façade */}
          <rect y="120" width="400" height="240" fill="#ffe2a8" stroke={INK} strokeWidth="4" />
          {[150, 190, 330].map((y, i) => <path key={y} d={`M${20 + i * 40} ${y} h44 M${300 - i * 20} ${y + 14} h40`} stroke={INK} strokeWidth="2.5" opacity=".18" strokeLinecap="round" />)}

          {/* Fenêtre */}
          <rect x="86" y="140" width="228" height="176" rx="12" fill="#fff" stroke={INK} strokeWidth="5" />
          <rect x="100" y="154" width="200" height="148" rx="6" fill="#4b3a8c" stroke={INK} strokeWidth="4" />
          <circle cx="200" cy="170" r="9" fill="#ffd23f" stroke={INK} strokeWidth="3" />
          <line x1="200" y1="154" x2="200" y2="161" stroke={INK} strokeWidth="3" />
          <path data-curtain d="M102 156 h44 q-6 40 -26 64 q-10 14 -18 18 z" fill="#ff6b9a" stroke={INK} strokeWidth="3.5" strokeLinejoin="round" />
          <path data-curtain d="M298 156 h-44 q6 40 26 64 q10 14 18 18 z" fill="#ff6b9a" stroke={INK} strokeWidth="3.5" strokeLinejoin="round" />

          {/* Mathilde */}
          <g onClick={poke} style={{ cursor: 'pointer' }}>
            <path d="M138 302 q0 -44 62 -46 q62 2 62 46 z" fill="#ffd23f" stroke={INK} strokeWidth="4" />
            <path d="M184 258 l16 14 l16 -14" fill="none" stroke={INK} strokeWidth="3" strokeLinejoin="round" />
            <g data-head>
              <path d="M152 220 q-6 44 10 58 h76 q16 -14 10 -58 z" fill={HAIR} stroke={INK} strokeWidth="4" />
              <circle cx="200" cy="222" r="38" fill={SKIN} stroke={INK} strokeWidth="4" />
              <path d="M162 214 q4 -36 38 -38 q36 2 40 38 q-14 -14 -30 -14 q-6 10 -26 12 q-12 -6 -22 2z" fill={HAIR} stroke={INK} strokeWidth="4" strokeLinejoin="round" />
              <circle cx="200" cy="172" r="15" fill={HAIR} stroke={INK} strokeWidth="4" />
              <path d="M188 180 q12 6 24 0" fill="none" stroke="#ff6b9a" strokeWidth="5" strokeLinecap="round" />
              <circle cx="163" cy="236" r="4.5" fill="#ffd23f" stroke={INK} strokeWidth="2" />
              <circle cx="237" cy="236" r="4.5" fill="#ffd23f" stroke={INK} strokeWidth="2" />
              <ellipse cx="180" cy="238" rx="7" ry="4.5" fill="#ff8fb1" opacity=".7" />
              <ellipse cx="220" cy="238" rx="7" ry="4.5" fill="#ff8fb1" opacity=".7" />
              <g>
                <ellipse cx="186" cy="224" rx="7" ry="8.5" fill="#fff" stroke={INK} strokeWidth="2.5" />
                <ellipse cx="214" cy="224" rx="7" ry="8.5" fill="#fff" stroke={INK} strokeWidth="2.5" />
                <g ref={pupils}>
                  <circle cx="186" cy="225" r="3.8" fill={INK} />
                  <circle cx="214" cy="225" r="3.8" fill={INK} />
                  <circle cx="187.5" cy="223.5" r="1.2" fill="#fff" />
                  <circle cx="215.5" cy="223.5" r="1.2" fill="#fff" />
                </g>
                <rect data-lid x="178" y="215" width="16" height="18" fill={SKIN} />
                <rect data-lid x="206" y="215" width="16" height="18" fill={SKIN} />
                <path d="M178 212 q8 -4 15 0 M207 212 q8 -4 15 0" fill="none" stroke={INK} strokeWidth="2.5" strokeLinecap="round" />
              </g>
              <path data-mouth d="M194 244 q6 4 12 0" fill="none" stroke={INK} strokeWidth="3" strokeLinecap="round" />
            </g>
            {/* Les mains sous le menton, coudes sur l'appui */}
            <path d="M150 300 q10 -34 36 -40" fill="none" stroke="#ffd23f" strokeWidth="18" strokeLinecap="round" />
            <path d="M250 300 q-10 -34 -36 -40" fill="none" stroke="#ffd23f" strokeWidth="18" strokeLinecap="round" />
            <path d="M150 300 q10 -34 36 -40 M250 300 q-10 -34 -36 -40" fill="none" stroke={INK} strokeWidth="3" opacity=".25" />
            <ellipse cx="188" cy="260" rx="12" ry="9" fill={SKIN} stroke={INK} strokeWidth="3" />
            <ellipse cx="212" cy="260" rx="12" ry="9" fill={SKIN} stroke={INK} strokeWidth="3" />
            <g data-sigh opacity="0" transform="translate(232 238)">
              <path d="M0 0 a8 8 0 0 1 14 -6 a7 7 0 0 1 12 6 h-26z" fill="#fff" stroke={INK} strokeWidth="2.5" />
              <text x="2" y="-18" fontFamily="Fredoka, sans-serif" fontWeight="700" fontSize="12" fill={INK}>pfff</text>
            </g>
            {[176, 200, 224].map((x, i) => (
              <path key={x} data-heart opacity="0" transform={`translate(${x} ${190 - i * 6})`} d="M0 4 C-8 -4 -4 -12 0 -6 C4 -12 8 -4 0 4z" fill="#ff6b9a" stroke={INK} strokeWidth="2" />
            ))}
          </g>

          {/* Appui de fenêtre + cactus */}
          <rect x="72" y="298" width="256" height="22" rx="7" fill="#fff" stroke={INK} strokeWidth="5" />
          <g data-cactus>
            <path d="M286 296 l-4 -20 h28 l-4 20z" fill="#ff8a3d" stroke={INK} strokeWidth="3.5" strokeLinejoin="round" />
            <path d="M296 276 v-28 a6 6 0 0 1 12 0 v28" fill="#2ec4b6" stroke={INK} strokeWidth="3.5" />
            <path d="M296 262 h-6 a4 4 0 0 1 -4 -4 v-6" fill="none" stroke={INK} strokeWidth="3.5" strokeLinecap="round" />
            <circle cx="302" cy="240" r="4" fill="#ff6b9a" stroke={INK} strokeWidth="2" />
          </g>
          <rect x="88" y="326" width="224" height="24" rx="7" fill="#fff" stroke={INK} strokeWidth="3" />
          <text x="200" y="342" textAnchor="middle" fontFamily="Fredoka, sans-serif" fontWeight="700" fontSize="13" fill={INK}>MATHILDE · AVENTURIÈRE RFP</text>
        </g>
      </svg>
    </div>
  )
}
