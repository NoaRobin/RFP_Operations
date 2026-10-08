/** Récit au défilement (ScrollTrigger) : chaque chapitre se révèle, le fil d'or avance avec la lecture. */
import { useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Play } from 'lucide-react'
import { Button } from '../components/ui/Button'
import { texts } from '../content/texts'
import { setSkipIntro } from '../lib/storage'
import { gsap, ScrollTrigger, SplitText, useGSAP } from '../motion/gsap'
import { d, ease, prefersReducedMotion } from '../motion/tokens'

export default function About() {
  const root = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  useGSAP(
    () => {
      const reduced = prefersReducedMotion()
      const title = new SplitText('[data-about-title]', { type: 'words' })
      gsap.from(title.words, { opacity: 0, y: reduced ? 0 : 40, stagger: 0.08, duration: d('epic'), ease: ease.out })

      gsap.to('[data-thread]', {
        scaleY: 1, ease: 'none',
        scrollTrigger: { trigger: '[data-chapters]', start: 'top 60%', end: 'bottom 60%', scrub: reduced ? false : 0.6 },
      })

      gsap.utils.toArray<HTMLElement>('[data-chapter]').forEach((chapter) => {
        const number = chapter.querySelector('[data-number]')
        const body = chapter.querySelectorAll('[data-line]')
        const tl = gsap.timeline({ scrollTrigger: { trigger: chapter, start: 'top 75%', toggleActions: 'play none none reverse' } })
        tl.from(number, { opacity: 0, scale: reduced ? 1 : 0.4, duration: d('slow'), ease: ease.spring })
          .from(body, { opacity: 0, y: reduced ? 0 : 30, stagger: 0.1, duration: d('slow'), ease: ease.out }, '<0.1')
        if (!reduced) {
          gsap.to(chapter.querySelector('[data-glyph]'), {
            yPercent: -40, rotate: 25, ease: 'none',
            scrollTrigger: { trigger: chapter, start: 'top bottom', end: 'bottom top', scrub: true },
          })
        }
      })
      ScrollTrigger.refresh()
      return () => title.revert()
    },
    { scope: root },
  )

  const glyphs = ['✦', '◈', '✧', '❖', '✺']
  return (
    <div ref={root} className="mx-auto w-[min(100%-2rem,64rem)] pt-20">
      <header className="min-h-[50vh]">
        <p className="eyebrow">{texts.about.eyebrow}</p>
        <h1 data-about-title className="mt-6 text-[clamp(3rem,9vw,7rem)] font-bold leading-[0.9] text-cartoon">{texts.about.title}</h1>
      </header>

      <div data-chapters className="relative">
        <span aria-hidden="true" className="absolute left-[1.45rem] top-0 h-full w-px bg-line-strong" />
        <span aria-hidden="true" data-thread className="absolute left-[1.45rem] top-0 h-full w-px origin-top scale-y-0 bg-gradient-to-b from-sun-400 via-magic-400 to-mint-400 shadow-[0_0_12px_var(--color-sun-400)]" />
        {texts.about.chapters.map((chapter, i) => (
          <section key={chapter.title} data-chapter className="relative grid min-h-[70vh] grid-cols-[3rem_1fr] gap-8 py-16">
            <span data-number className="relative z-10 grid size-12 place-items-center rounded-full border border-sun-400/50 bg-canvas font-display text-xl text-sun-300 shadow-[var(--shadow-glow-sun)]">
              {i + 1}
            </span>
            <div className="relative">
              <span data-glyph aria-hidden="true" className="pointer-events-none absolute -right-2 -top-6 font-display text-[8rem] leading-none text-magic-500/15 sm:text-[12rem]">{glyphs[i % glyphs.length]}</span>
              <h2 data-line className="text-[clamp(2rem,5vw,3.5rem)] font-bold leading-tight">{chapter.title}</h2>
              <p data-line className="mt-6 max-w-2xl text-xl leading-relaxed text-fg-2">{chapter.body}</p>
            </div>
          </section>
        ))}
      </div>

      <footer className="flex flex-col items-center gap-6 py-24 text-center">
        <Button variant="primary" size="lg" icon={<Play size={18} />} onClick={() => {
          setSkipIntro(false)
          navigate('/intro')
        }}>
          {texts.about.replayIntro}
        </Button>
        <p className="text-fg-3">{texts.about.credits}</p>
      </footer>
    </div>
  )
}
