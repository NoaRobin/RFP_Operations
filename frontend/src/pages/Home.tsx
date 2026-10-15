/**
 * Accueil « RFP pas envie de travailler » : le livre vivant, la course-poursuite, Mathilde à sa fenêtre, et en plein milieu, le cri de ralliement #RFPasenviedetravailler,
 * entouré des automatisations en autocollants. Lettres qui rebondissent (SplitText), autocollants qui flottent.
 */
import { useMemo, useRef } from 'react'
import { Link } from 'react-router-dom'
import { Activity, ArrowRight, Command, FileQuestion, FileSpreadsheet, Paintbrush, Sparkles, Tags } from 'lucide-react'
import { Chase } from '../components/fx/Chase'
import { Mathilde } from '../components/fx/Mathilde'
import { useApp } from '../components/layout/AppContext'
import { Stage } from '../components/three/Stage'
import { ButtonLink } from '../components/ui/Button'
import { CountUp } from '../components/ui/CountUp'
import { useToast } from '../components/ui/Toast'
import { texts, pick } from '../content/texts'
import { api } from '../lib/api'
import { greeting } from '../lib/format'
import { useAsync } from '../lib/hooks'
import { useUserName } from '../lib/storage'
import { gsap, SplitText, useGSAP } from '../motion/gsap'
import { d, ease, prefersReducedMotion } from '../motion/tokens'

const STICKERS = [
  { to: '/rfi', label: texts.home.stickers.rfi, icon: FileQuestion, bg: 'bg-sun-400', pos: 'lg:left-[2%] lg:top-[8%]', rot: -7 },
  { to: '/merge-codes', label: texts.home.stickers.merge, icon: Tags, bg: 'bg-bubble-400', pos: 'lg:right-[3%] lg:top-[4%]', rot: 6 },
  { to: '/suivi-activite', label: texts.home.stickers.suivi, icon: Activity, bg: 'bg-mint-400', pos: 'lg:left-[0%] lg:bottom-[14%]', rot: 5 },
  { to: '/rfpascontente', label: texts.home.stickers.sorts, icon: Paintbrush, bg: 'bg-magic-400', pos: 'lg:right-[1%] lg:bottom-[20%]', rot: -5 },
  { to: '/atelier', label: texts.home.stickers.atelier, icon: FileSpreadsheet, bg: 'bg-card', pos: 'lg:left-[16%] lg:-bottom-[2%]', rot: -3 },
] as const

const MODULES = [
  { to: '/rfi', icon: FileQuestion, color: 'bg-sun-400', ...texts.home.cards.rfi },
  { to: '/merge-codes', icon: Tags, color: 'bg-bubble-400', ...texts.home.cards.merge },
  { to: '/suivi-activite', icon: Activity, color: 'bg-mint-400', ...texts.home.cards.suivi },
  { to: '/rfpascontente', icon: Paintbrush, color: 'bg-magic-400', ...texts.home.cards.sorts },
]

export default function Home() {
  const root = useRef<HTMLDivElement>(null)
  const name = useUserName()
  const toast = useToast()
  const { openPalette } = useApp()
  const { data } = useAsync(() => api.dashboard(), [])
  const pokes = useRef(0)
  const joke = useMemo(() => pick(texts.home.jokes), [])

  useGSAP(
    () => {
      if (prefersReducedMotion()) {
        gsap.from('[data-fade]', { opacity: 0, duration: d('fast') })
        return
      }
      const split = new SplitText('[data-hashtag] [data-line]', { type: 'chars', charsClass: 'inline-block will-change-transform' })
      const tl = gsap.timeline({ delay: 0.15 })
      tl.from('[data-stage]', { scale: 0.4, opacity: 0, duration: d('slow'), ease: ease.spring })
        .from(split.chars, {
          y: () => gsap.utils.random(-160, -60), rotation: () => gsap.utils.random(-40, 40), opacity: 0, scale: 0.4,
          duration: 0.9, ease: 'bounce.out', stagger: { each: 0.035, from: 'random' },
        }, 0.2)
        .from('[data-fade]', { opacity: 0, y: 18, stagger: 0.08, duration: d('slow'), ease: ease.out }, 0.7)
        .from('[data-sticker]', { scale: 0, rotation: 0, opacity: 0, stagger: 0.09, duration: d('slow'), ease: 'back.out(2.4)' }, 0.9)
      // Les autocollants flottent, chacun à son rythme
      gsap.utils.toArray<HTMLElement>('[data-sticker]').forEach((el, i) => {
        gsap.to(el, { y: i % 2 ? -10 : 10, duration: 2 + i * 0.35, yoyo: true, repeat: -1, ease: ease.breathe, delay: 1.6 })
      })
      // Chaque lettre saute quand on la survole
      const handlers = split.chars.map((char) => {
        const jump = () => gsap.fromTo(char, { y: 0 }, { y: -26, rotation: gsap.utils.random(-14, 14), duration: 0.22, yoyo: true, repeat: 1, ease: 'power2.out', overwrite: true })
        char.addEventListener('pointerenter', jump)
        return () => char.removeEventListener('pointerenter', jump)
      })
      // Cartes au défilement
      gsap.from('[data-card]', { y: 50, opacity: 0, rotation: () => gsap.utils.random(-4, 4), stagger: 0.1, duration: d('slow'), ease: 'back.out(1.6)', scrollTrigger: { trigger: '[data-cards]', start: 'top 85%', once: true } })
      return () => {
        handlers.forEach((off) => off())
        split.revert()
      }
    },
    { scope: root },
  )

  const poke = () => {
    pokes.current += 1
    if (pokes.current % 3 === 0) toast('magic', pick(texts.easterEggs.orb, pokes.current / 3 - 1))
  }

  const counters = data?.counters
  return (
    <div ref={root} className="mx-auto w-[min(100%-2rem,82rem)] pt-6 sm:pt-10">
      <section aria-labelledby="hashtag" className="relative flex flex-col items-center text-center lg:min-h-[44rem]">
        <p data-fade className="eyebrow"><Sparkles size={13} aria-hidden="true" />{greeting()}{name ? `, ${name}` : ''} · {texts.home.kicker}</p>

        <div data-stage className="relative mt-2 h-[15rem] w-[min(100%,24rem)] sm:h-[17rem]">
          <Stage mood="calm" onPoke={poke} className="absolute inset-0" />
        </div>

        <h1 id="hashtag" data-hashtag aria-label={texts.app.hashtag}
          className="text-cartoon relative z-10 -mt-4 select-none font-display font-bold leading-[0.88] tracking-tight text-[clamp(2.6rem,10.5vw,8.6rem)]">
          <span data-line aria-hidden="true" className="block">#RFPasenvie</span>
          <span data-line aria-hidden="true" className="block text-[var(--color-bubble-400)]">detravailler</span>
        </h1>

        <p data-fade className="mt-6 max-w-2xl text-lg font-semibold text-fg-2 sm:text-xl">{texts.home.lead}</p>
        <div data-fade className="mt-7 flex flex-wrap justify-center gap-3">
          <ButtonLink to="/rfi" variant="primary" size="lg" icon={<FileQuestion size={20} />}>{texts.home.ctaRfi}</ButtonLink>
          <ButtonLink to="/rfpascontente" size="lg" icon={<Paintbrush size={20} />}>{texts.home.ctaSorts}</ButtonLink>
        </div>

        {/* Les automatisations, en autocollants autour du hashtag (en ligne sur mobile) */}
        <ul className="mt-10 flex flex-wrap justify-center gap-3 lg:mt-0" aria-label={texts.home.modules}>
          {STICKERS.map(({ to, label, icon: Icon, bg, pos, rot }) => (
            <li key={to} className={`lg:absolute ${pos}`}>
              <Link data-sticker to={to} style={{ rotate: `${rot}deg` }}
                className={`group inline-flex items-center gap-2 rounded-2xl border-[2.5px] border-fg ${bg} px-4 py-2.5 font-display text-base font-semibold text-fg shadow-[4px_4px_0_0_var(--color-fg)] transition-[box-shadow,scale] duration-[var(--duration-fast)] hover:scale-110 hover:shadow-[6px_6px_0_0_var(--color-fg)] sm:text-lg`}>
                <Icon size={20} aria-hidden="true" className="transition-transform duration-[var(--duration-base)] ease-[var(--ease-spring)] group-hover:-rotate-12" />
                {label}
              </Link>
            </li>
          ))}
          <li className="lg:absolute lg:right-[14%] lg:-bottom-[1%]">
            <button data-sticker onClick={openPalette} style={{ rotate: '4deg' }}
              className="inline-flex items-center gap-2 rounded-2xl border-[2.5px] border-dashed border-fg bg-canvas px-4 py-2.5 font-display font-semibold text-fg-2 hover:text-fg">
              <Command size={18} aria-hidden="true" />{texts.home.stickers.palette}
            </button>
          </li>
        </ul>
      </section>

      {/* La course-poursuite livres / appels d'offres */}
      <section aria-label={texts.home.chase.title} className="mt-16">
        <Chase />
      </section>

      {/* Compteurs */}
      <section aria-label="Compteurs" className="mt-10 grid gap-4 sm:grid-cols-3">
        {[
          { value: counters?.spells_total ?? 0, label: texts.home.stats.spells, color: 'bg-sun-400', digits: 0 },
          { value: (counters?.minutes_saved_total ?? 0) / 60, label: texts.home.stats.hours, color: 'bg-mint-400', digits: 1 },
          { value: counters?.spells_week ?? 0, label: texts.home.stats.week, color: 'bg-bubble-400', digits: 0 },
        ].map((c, i) => (
          <div key={c.label} className="card-pop flex items-center gap-4 rounded-[var(--radius-card)] p-5" style={{ rotate: `${[-1, 0.8, -0.6][i]}deg` }}>
            <span className={`grid size-12 shrink-0 place-items-center rounded-full border-[2.5px] border-fg ${c.color} font-display text-xl font-bold`} aria-hidden="true">{['✦', '⏱', '★'][i]}</span>
            <p className="flex flex-col">
              <CountUp value={c.value} digits={c.digits} className="font-display text-4xl font-bold text-fg" />
              <span className="text-sm font-semibold text-fg-2">{c.label}</span>
            </p>
          </div>
        ))}
      </section>

      {/* Modules */}
      <section aria-labelledby="modules-title" className="mt-20">
        <h2 id="modules-title" className="text-4xl sm:text-5xl">{texts.home.modules}</h2>
        <div data-cards className="mt-8 grid gap-6 sm:grid-cols-2">
          {MODULES.map(({ to, icon: Icon, color, title, body, tag }) => (
            <Link data-card key={to} to={to} className="card-pop group relative flex flex-col gap-3 rounded-[var(--radius-card)] p-7">
              <span className="absolute right-5 top-5 rounded-full border-2 border-fg bg-canvas px-3 py-0.5 text-xs font-bold uppercase tracking-wider">{tag}</span>
              <span className={`grid size-16 place-items-center rounded-2xl border-[2.5px] border-fg ${color} shadow-[3px_3px_0_0_var(--color-fg)] transition-transform duration-[var(--duration-base)] ease-[var(--ease-spring)] group-hover:-rotate-6 group-hover:scale-110`}>
                <Icon size={30} aria-hidden="true" />
              </span>
              <h3 className="mt-2 text-3xl">{title}</h3>
              <p className="text-fg-2">{body}</p>
              <span className="mt-auto inline-flex items-center gap-1.5 pt-2 font-display font-semibold text-magic-300">
                Ouvrir <ArrowRight size={18} className="transition-transform group-hover:translate-x-1.5" aria-hidden="true" />
              </span>
            </Link>
          ))}
        </div>
      </section>

      {/* Mathilde à sa fenêtre */}
      <section aria-labelledby="mathilde-title" className="mt-24 grid items-center gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Mathilde className="mx-auto w-full max-w-md" />
        <div>
          <p className="eyebrow">{texts.home.mathilde.eyebrow}</p>
          <h2 id="mathilde-title" className="mt-4 text-4xl sm:text-5xl">{texts.home.mathilde.title}</h2>
          <p className="mt-4 text-lg font-semibold text-fg-2">{texts.home.mathilde.body}</p>
        </div>
      </section>

      <p className="mt-16 text-center font-display text-lg italic text-fg-3">« {joke} »</p>
    </div>
  )
}
