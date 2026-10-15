/** 404 : un apprenti s'est téléporté de travers. Mathilde le cherche par la fenêtre ; le bouton de retour reste évident. */
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
      gsap.to('[data-frog]', { y: -22, duration: 0.45, yoyo: true, repeat: -1, ease: 'power2.out', repeatDelay: 0.6 })
      gsap.to('[data-q]', { rotate: 18, transformOrigin: '50% 100%', duration: 0.8, yoyo: true, repeat: -1, ease: ease.breathe })
    },
    { scope: root },
  )

  return (
    <div ref={root} className="mx-auto flex min-h-[70vh] w-[min(100%-2rem,48rem)] flex-col items-center justify-center pt-12 text-center">
      <svg data-enter viewBox="0 0 220 170" className="w-64" role="img" aria-label="Un crapaud perplexe : l'apprenti transformé">
        <ellipse cx="110" cy="152" rx="60" ry="8" fill="#1b1530" opacity=".15" />
        <g data-frog>
          <ellipse cx="110" cy="110" rx="56" ry="38" fill="#2ec4b6" stroke="#1b1530" strokeWidth="4" />
          <circle cx="86" cy="74" r="17" fill="#2ec4b6" stroke="#1b1530" strokeWidth="4" />
          <circle cx="134" cy="74" r="17" fill="#2ec4b6" stroke="#1b1530" strokeWidth="4" />
          <circle cx="86" cy="74" r="9" fill="#fff" stroke="#1b1530" strokeWidth="3" />
          <circle cx="134" cy="74" r="9" fill="#fff" stroke="#1b1530" strokeWidth="3" />
          <circle cx="88" cy="76" r="4" fill="#1b1530" />
          <circle cx="132" cy="76" r="4" fill="#1b1530" />
          <path d="M88 116 q22 14 44 0" fill="none" stroke="#1b1530" strokeWidth="4" strokeLinecap="round" />
          <path d="M76 46 L110 6 L144 46 Z" fill="#7c5cff" stroke="#1b1530" strokeWidth="4" strokeLinejoin="round" />
          <circle cx="112" cy="30" r="4" fill="#ffd23f" stroke="#1b1530" strokeWidth="2" />
        </g>
        <text data-q x="176" y="60" fill="#ff6b9a" stroke="#1b1530" strokeWidth="2" fontSize="42" fontWeight="700" fontFamily="Fredoka, sans-serif">?</text>
      </svg>
      <p data-enter className="mt-8 rounded-full border-2 border-fg bg-sun-400 px-3 py-1 text-xs font-bold uppercase tracking-[0.2em]">{texts.errors.notFoundCode}</p>
      <h1 data-enter className="mt-4 text-[clamp(2.5rem,6vw,4.25rem)] font-bold leading-none">{texts.errors.notFoundTitle}</h1>
      <p data-enter className="mt-4 max-w-lg text-lg font-semibold text-fg-2">{texts.errors.notFoundBody}</p>
      <div data-enter className="mt-8">
        <ButtonLink to="/" variant="primary" size="lg" icon={<ArrowLeft size={18} />}>{texts.errors.notFoundCta}</ButtonLink>
      </div>
    </div>
  )
}
