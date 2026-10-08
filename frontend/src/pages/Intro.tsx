import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, SkipForward } from 'lucide-react'
import { Stage } from '../components/three/Stage'
import type { Mood } from '../components/three/moods'
import { Button } from '../components/ui/Button'
import { useToast } from '../components/ui/Toast'
import { texts, pick } from '../content/texts'
import { setSkipIntro, shouldSkipIntro } from '../lib/storage'
import { gsap, SplitText, useGSAP } from '../motion/gsap'
import { d, ease, prefersReducedMotion, stagger } from '../motion/tokens'

function markSeen() {
  try {
    sessionStorage.setItem('rfppasenvie.intro.seen', '1')
  } catch {
    /* rien */
  }
}

export default function Intro() {
  const root = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const toast = useToast()
  const [mood, setMood] = useState<Mood>('calm')
  const [remember, setRemember] = useState(shouldSkipIntro())
  const pokes = useRef(0)
  const leaving = useRef(false)

  useGSAP(
    () => {
      const reduced = prefersReducedMotion()
      if (reduced) {
        // Mouvement réduit : tout est là tout de suite, un simple fondu suffit.
        gsap.from('[data-stage], [data-copy]', { opacity: 0, duration: d('fast') })
        setMood('awaken')
        return
      }
      const title = new SplitText('[data-title]', { type: 'chars', charsClass: 'inline-block will-change-transform' })
      const subtitle = new SplitText('[data-subtitle]', { type: 'words', wordsClass: 'inline-block' })
      const tl = gsap.timeline({ delay: 0.3 })
      tl.from('[data-stage]', { opacity: 0, scale: reduced ? 1 : 0.6, duration: d('epic'), ease: ease.out })
        .call(() => setMood('awaken'), [], 0.5)
        .from('[data-eyebrow]', { opacity: 0, y: reduced ? 0 : 10, duration: d('slow') }, 0.7)
        .from(title.chars, {
          opacity: 0, yPercent: reduced ? 0 : 110, rotateX: reduced ? 0 : -80, filter: 'blur(8px)',
          stagger: stagger.base, duration: d('epic'), ease: ease.out,
        }, 0.8)
        .from(subtitle.words, { opacity: 0, y: reduced ? 0 : 14, stagger: stagger.base, duration: d('slow') }, 1.5)
        .from('[data-actions] > *', { opacity: 0, y: reduced ? 0 : 16, stagger: stagger.loose, duration: d('slow') }, 1.9)
        .call(() => setMood('calm'), [], 3.2)
      return () => {
        title.revert()
        subtitle.revert()
      }
    },
    { scope: root },
  )

  const enter = () => {
    if (leaving.current) return
    leaving.current = true
    setSkipIntro(remember)
    markSeen()
    setMood('success')
    const reduced = prefersReducedMotion()
    gsap.timeline({ onComplete: () => navigate('/', { replace: true }) })
      .to('[data-copy]', { opacity: 0, y: reduced ? 0 : -20, duration: d('base'), ease: ease.in })
      .to('[data-stage]', { scale: reduced ? 1 : 3.2, opacity: 0, duration: d('slow'), ease: ease.in }, reduced ? 0 : 0.25)
      .to('[data-flash]', { opacity: 1, duration: d('fast') }, '-=0.25')
  }

  const skip = () => {
    setSkipIntro(remember)
    markSeen()
    navigate('/', { replace: true })
  }

  const poke = () => {
    pokes.current += 1
    if (pokes.current % 3 === 0) toast('magic', pick(texts.easterEggs.orb, pokes.current / 3 - 1))
  }

  return (
    <div ref={root} className="relative grid min-h-dvh place-items-center overflow-hidden px-6">
      <button
        onClick={skip}
        className="absolute right-5 top-5 z-20 inline-flex items-center gap-2 rounded-full border-2 border-fg bg-card px-4 py-2 text-sm font-bold text-fg-2 hover:text-fg transition-colors"
      >
        <SkipForward size={16} aria-hidden="true" />
        {texts.intro.skip}
      </button>

      <div data-stage className="absolute inset-0">
        <Stage mood={mood} onPoke={poke} className="relative size-full" />
      </div>
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(255,246,229,0.0)_0%,rgba(255,246,229,0.0)_45%,rgba(255,246,229,0.9)_85%)]"
      />

      <div data-copy className="relative z-10 flex flex-col items-center text-center pointer-events-none">
        <p data-eyebrow className="eyebrow">{texts.intro.eyebrow}</p>
        <h1 data-title className="mt-6 font-display text-[clamp(2.5rem,8vw,7rem)] leading-[0.95] font-bold tracking-[0.02em] text-cartoon [perspective:600px]">
          {texts.app.name}
        </h1>
        <p data-subtitle className="mt-6 max-w-xl font-display text-[clamp(1.25rem,2.6vw,1.75rem)] font-semibold text-magic-300">
          {texts.app.hashtag}
        </p>
        <div data-actions className="pointer-events-auto mt-12 flex flex-col items-center gap-5">
          <Button variant="primary" size="lg" onClick={enter} icon={<ArrowRight size={18} />} autoFocus>
            {texts.intro.enter}
          </Button>
          <label className="flex items-center gap-2 text-sm text-fg-2 cursor-pointer">
            <input
              type="checkbox"
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
              className="size-4 accent-[var(--color-sun-400)]"
            />
            {texts.intro.remember}
          </label>
          <p className="text-xs text-fg-3">{texts.intro.orbHint}</p>
        </div>
      </div>
      <div data-flash aria-hidden="true" className="pointer-events-none absolute inset-0 z-30 bg-canvas opacity-0" />
    </div>
  )
}
