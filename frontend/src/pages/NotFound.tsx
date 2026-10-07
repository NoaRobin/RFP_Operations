/** 404 : un apprenti sorcier perdu, son chapeau et quelques étoiles. Le bouton de retour reste évident. */
import { useRef } from 'react'
import { ArrowLeft } from 'lucide-react'
import { ButtonLink } from '../components/ui/Button'
import { texts } from '../content/texts'
import { gsap, useGSAP } from '../motion/gsap'
import { d, ease, prefersReducedMotion } from '../motion/tokens'

export default function NotFound() {
  const root = useRef<HTMLDivElement>(null)
  useGSAP(
    () => {
      gsap.from('[data-enter]', { opacity: 0, y: 24, stagger: 0.1, duration: d('slow'), ease: ease.out })
      if (prefersReducedMotion()) return
      gsap.to('[data-apprentice]', { rotate: 6, y: -6, duration: 1.6, yoyo: true, repeat: -1, ease: ease.breathe, transformOrigin: '50% 100%' })
      gsap.to('[data-question]', { y: -10, opacity: 0.4, duration: 1.2, yoyo: true, repeat: -1, stagger: 0.3, ease: ease.breathe })
      gsap.to('[data-wand-spark]', { scale: 1.8, opacity: 0, duration: 0.9, repeat: -1, ease: 'power2.out', transformOrigin: 'center' })
    },
    { scope: root },
  )

  return (
    <div ref={root} className="mx-auto flex min-h-[70vh] w-[min(100%-2rem,48rem)] flex-col items-center justify-center pt-12 text-center">
      <svg data-enter viewBox="0 0 200 200" className="w-56" role="img" aria-label="Un apprenti sorcier perdu, l'air perplexe">
        <ellipse cx="100" cy="182" rx="50" ry="6" fill="rgba(139,92,246,0.25)" />
        <g data-apprentice>
          <path d="M100 18 L132 112 L68 112 Z" fill="#2a1b5e" stroke="#a78bfa" strokeWidth="2" />
          <path d="M104 30 l3 8 8 3 -8 3 -3 8 -3 -8 -8 -3 8 -3z" fill="#f5dfa5" />
          <circle cx="86" cy="70" r="2" fill="#f5dfa5" /><circle cx="112" cy="88" r="2.5" fill="#5eead4" />
          <ellipse cx="100" cy="112" rx="46" ry="9" fill="#3b2a7a" stroke="#a78bfa" strokeWidth="2" />
          <path d="M70 120 Q100 190 130 120 Z" fill="#1d1940" stroke="#a78bfa" strokeWidth="2" />
          <circle cx="90" cy="132" r="3" fill="#f4efff" /><circle cx="110" cy="132" r="3" fill="#f4efff" />
          <path d="M92 146 q8 -5 16 0" stroke="#f4efff" strokeWidth="2" fill="none" strokeLinecap="round" />
          <line x1="132" y1="140" x2="160" y2="118" stroke="#e8c77a" strokeWidth="3" strokeLinecap="round" />
          <circle data-wand-spark cx="160" cy="118" r="4" fill="#f5dfa5" />
        </g>
        <text data-question x="40" y="60" fill="#c4b5fd" fontSize="26" fontFamily="Georgia, serif">?</text>
        <text data-question x="150" y="50" fill="#5eead4" fontSize="20" fontFamily="Georgia, serif">?</text>
      </svg>
      <p data-enter className="mt-8 font-mono text-xs uppercase tracking-[0.25em] text-gold-300">{texts.errors.notFoundCode}</p>
      <h1 data-enter className="mt-4 text-[clamp(2.25rem,6vw,4rem)] font-light">{texts.errors.notFoundTitle}</h1>
      <p data-enter className="mt-4 max-w-lg text-lg text-mist">{texts.errors.notFoundBody}</p>
      <div data-enter className="mt-8">
        <ButtonLink to="/" variant="primary" size="lg" icon={<ArrowLeft size={18} />}>{texts.errors.notFoundCta}</ButtonLink>
      </div>
    </div>
  )
}
