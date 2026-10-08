import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { ArrowRight, FileSpreadsheet, Lightbulb, Search, Star, TriangleAlert } from 'lucide-react'
import { AutomationCard } from '../components/AutomationCard'
import { useApp } from '../components/layout/AppContext'
import { Button, ButtonLink } from '../components/ui/Button'
import { EmptyState, ErrorState, Skeleton } from '../components/ui/States'
import { useTilt } from '../components/ui/useTilt'
import { texts, pick } from '../content/texts'
import { api } from '../lib/api'
import { greeting } from '../lib/format'
import { useAsync, useHotkey } from '../lib/hooks'
import { useFavorites, useUserName } from '../lib/storage'
import { Flip, gsap, ScrollTrigger, SplitText, useGSAP } from '../motion/gsap'
import { d, dist, ease, prefersReducedMotion, stagger } from '../motion/tokens'

const FAVORITES = '__favorites__'
const ALL = '__all__'

function normalize(text: string) {
  return text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
}

function FeaturedAtelier() {
  const ref = useTilt<HTMLDivElement>(3)
  return (
    <div ref={ref} className="halo relative overflow-hidden rounded-[calc(var(--radius-card)*1.4)] glass p-8 sm:p-10" data-reveal>
      <div aria-hidden="true" className="absolute -right-16 -top-24 size-80 rounded-full bg-[radial-gradient(circle,rgb(255_210_63/0.45),transparent_65%)] blur-2xl" />
      <div aria-hidden="true" className="absolute right-6 top-6 hidden sm:grid grid-cols-6 gap-1.5 opacity-60" style={{ transform: 'translateZ(40px)' }}>
        {Array.from({ length: 24 }, (_, i) => (
          <span key={i} className={`h-5 w-9 rounded-sm border ${[3, 8, 9, 14, 20].includes(i) ? 'border-mint-400/70 bg-mint-400/15 animate-pulse-glow' : 'border-line-strong bg-fg/[0.02]'}`} />
        ))}
      </div>
      <p className="eyebrow">{texts.library.featuredEyebrow}</p>
      <h2 className="mt-3 flex items-center gap-3 text-4xl sm:text-5xl">
        <FileSpreadsheet className="text-sun-300" size={36} aria-hidden="true" />
        {texts.library.featuredTitle}
      </h2>
      <p className="mt-4 max-w-2xl text-lg text-fg-2">{texts.library.featuredBody}</p>
      <ButtonLink to="/atelier" variant="primary" size="lg" className="mt-8" icon={<ArrowRight size={18} />}>
        {texts.library.featuredCta}
      </ButtonLink>
    </div>
  )
}

export default function Library() {
  const { data, error, loading, reload } = useAsync(() => api.automations(), [])
  const { health, openSuggest } = useApp()
  const name = useUserName()
  const [favorites, toggleFavorite] = useFavorites()
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState(ALL)
  const root = useRef<HTMLDivElement>(null)
  const grid = useRef<HTMLDivElement>(null)
  const search = useRef<HTMLInputElement>(null)
  const flipState = useRef<Flip.FlipState | null>(null)
  const subtitle = useMemo(() => pick(texts.greeting.subtitles), [])

  useHotkey('/', (e) => {
    e.preventDefault()
    search.current?.focus()
  })

  const automations = data?.automations ?? []
  const categories = useMemo(() => [...new Set(automations.map((a) => a.category))].sort(), [automations])
  const visible = useMemo(() => {
    const q = normalize(query.trim())
    return new Set(
      automations
        .filter((a) => category === ALL || (category === FAVORITES ? favorites.has(a.id) : a.category === category))
        .filter((a) => !q || normalize([a.name, a.description, a.category, ...a.tags].join(' ')).includes(q))
        .map((a) => a.id),
    )
  }, [automations, query, category, favorites])

  // Flip : photo avant filtrage…
  const changeFilter = (update: () => void) => {
    if (grid.current) flipState.current = Flip.getState(grid.current.querySelectorAll('[data-item]'))
    update()
  }
  // …animation après.
  useLayoutEffect(() => {
    const state = flipState.current
    if (!state || !grid.current) return
    flipState.current = null
    Flip.from(state, {
      targets: grid.current.querySelectorAll('[data-item]'),
      duration: d('slow'),
      ease: ease.inOut,
      absolute: true,
      scale: true,
      stagger: stagger.tight,
      onEnter: (els) => gsap.fromTo(els, { opacity: 0, scale: 0.92 }, { opacity: 1, scale: 1, y: 0, duration: d('base'), ease: ease.out }),
      onLeave: (els) => gsap.to(els, { opacity: 0, scale: 0.92, duration: d('fast'), ease: ease.in }),
    })
  }, [visible])

  // Titre + révélations au scroll
  useGSAP(
    () => {
      if (prefersReducedMotion()) {
        // Mouvement réduit : contenu visible immédiatement, aucun masquage au défilement.
        gsap.from('[data-hero-title], [data-hero-sub]', { opacity: 0, duration: d('fast') })
        return
      }
      const split = new SplitText('[data-hero-title]', { type: 'lines,words', linesClass: 'overflow-hidden pb-1' })
      gsap.from(split.words, { yPercent: 100, opacity: 0, duration: d('epic'), ease: ease.out, stagger: stagger.base })
      gsap.from('[data-hero-sub]', { opacity: 0, y: dist('lift'), duration: d('slow'), delay: 0.35 })
      gsap.utils.toArray<HTMLElement>('[data-reveal]').forEach((el) => {
        gsap.from(el, { opacity: 0, y: dist('fall'), duration: d('slow'), scrollTrigger: { trigger: el, start: 'top 88%', once: true } })
      })
      return () => split.revert()
    },
    { scope: root },
  )
  useLayoutEffect(() => {
    if (!data || !grid.current || prefersReducedMotion()) return
    const items = grid.current.querySelectorAll('[data-item]')
    gsap.set(items, { opacity: 0, y: dist('fall') })
    const batch = ScrollTrigger.batch(items, {
      start: 'top 95%',
      once: true,
      onEnter: (els) => gsap.to(els, { opacity: 1, y: 0, stagger: stagger.base, duration: d('slow'), ease: ease.out, overwrite: 'auto' }),
    })
    ScrollTrigger.refresh()
    return () => batch.forEach((t) => t.kill())
  }, [data])

  const chip = (value: string, label: React.ReactNode) => (
    <button
      key={value}
      onClick={() => changeFilter(() => setCategory(value))}
      aria-pressed={category === value}
      className={`inline-flex items-center gap-1.5 rounded-full border-2 px-4 py-2 text-sm font-bold transition-all duration-[var(--duration-fast)] ${
        category === value
          ? 'border-fg bg-sun-400 text-fg shadow-[2px_2px_0_0_var(--color-fg)]'
          : 'border-fg/25 bg-card text-fg-2 hover:text-fg hover:border-fg'}`}
    >
      {label}
    </button>
  )

  return (
    <div ref={root} className="mx-auto w-[min(100%-2rem,82rem)] pt-16 sm:pt-24">
      <section aria-labelledby="hero-title" className="max-w-4xl">
        <p className="eyebrow">{texts.library.eyebrow}</p>
        <h1 id="hero-title" data-hero-title className="mt-4 text-[clamp(2.75rem,7vw,5.5rem)] font-bold leading-[0.95]">
          {greeting()}{name ? `, ${name}` : ''}.
          <br />
          <span className="text-cartoon">{texts.greeting.question}</span>
        </h1>
        <p data-hero-sub className="mt-6 max-w-2xl text-lg text-fg-2">{subtitle}</p>
      </section>

      <div className="mt-14">
        <FeaturedAtelier />
      </div>

      <section aria-labelledby="spells-title" className="mt-20">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between" data-reveal>
          <div>
            <h2 id="spells-title" className="text-4xl">{texts.library.title}</h2>
            <p className="mt-2 text-fg-2">
              {texts.library.available(automations.length)}
              {health?.data_mode === 'mock' && <span className="text-sun-300"> · {texts.app.demoBadge.toLowerCase()}</span>}
            </p>
          </div>
          <div className="relative w-full lg:w-96">
            <label htmlFor="spell-search" className="sr-only">{texts.library.searchLabel}</label>
            <Search className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-fg-3" size={18} aria-hidden="true" />
            <input
              id="spell-search"
              ref={search}
              type="search"
              value={query}
              onChange={(e) => changeFilter(() => setQuery(e.target.value))}
              placeholder={texts.library.searchPlaceholder}
              className="h-12 w-full rounded-full border-2 border-fg bg-card pl-11 pr-4 font-semibold text-fg placeholder:text-fg-3 transition-[border-color,box-shadow] duration-[var(--duration-fast)] focus:outline-none focus:shadow-[3px_3px_0_0_var(--color-magic-500)]"
            />
          </div>
        </div>

        <div role="group" aria-label="Filtrer par catégorie" className="mt-6 flex flex-wrap gap-2" data-reveal>
          {chip(ALL, texts.library.all)}
          {chip(FAVORITES, <><Star size={14} aria-hidden="true" />{texts.library.favorites} ({favorites.size})</>)}
          {categories.map((c) => chip(c, c))}
        </div>

        {error && <ErrorState error={error} onRetry={reload} />}
        {loading && !data && (
          <div className="mt-8 grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
            {[0, 1, 2].map((i) => <Skeleton key={i} className="h-72" />)}
          </div>
        )}

        {data && (
          <>
            <div ref={grid} className="mt-8 grid gap-6 sm:grid-cols-2 xl:grid-cols-3" aria-live="polite">
              {automations.map((a) => (
                <div key={a.id} data-item className={visible.has(a.id) ? '' : 'hidden'}>
                  <AutomationCard automation={a} favorite={favorites.has(a.id)} onToggleFavorite={() => toggleFavorite(a.id)} />
                </div>
              ))}
              <div data-item className={category === ALL && !query ? '' : 'hidden'}>
                <button
                  onClick={openSuggest}
                  className="group flex h-full min-h-72 w-full flex-col items-start justify-end rounded-[var(--radius-card)] border-[2.5px] border-dashed border-fg/40 bg-card/60 p-6 text-left transition-all duration-[var(--duration-base)] hover:border-sun-400 hover:bg-sun-400/5"
                >
                  <Lightbulb className="text-sun-300 transition-transform duration-[var(--duration-slow)] ease-[var(--ease-spring)] group-hover:-rotate-12 group-hover:scale-110" size={32} aria-hidden="true" />
                  <span className="mt-4 font-display text-2xl text-fg">{texts.library.suggestCardTitle}</span>
                  <span className="mt-2 text-fg-2">{texts.library.suggestCardBody}</span>
                </button>
              </div>
            </div>
            {visible.size === 0 && (category === FAVORITES && !query ? (
              <EmptyState title={texts.library.emptyFavorites.title} body={texts.library.emptyFavorites.body} />
            ) : (
              <EmptyState
                title={texts.library.emptySearch.title}
                body={texts.library.emptySearch.body}
                action={
                  <div className="flex flex-wrap justify-center gap-3">
                    <Button onClick={() => changeFilter(() => { setQuery(''); setCategory(ALL) })}>{texts.library.emptySearch.reset}</Button>
                    <Button variant="ghost" onClick={openSuggest}>{texts.nav.suggest}</Button>
                  </div>
                }
              />
            ))}
            {data.broken.length > 0 && (
              <div className="mt-12 rounded-[var(--radius-card)] border border-warning/30 bg-warning/5 p-6" role="note">
                <h3 className="flex items-center gap-2 text-xl"><TriangleAlert className="text-warning" size={20} aria-hidden="true" />{texts.library.brokenTitle}</h3>
                <p className="mt-2 text-fg-2">{texts.library.brokenBody}</p>
                <ul className="mt-3 space-y-1 font-mono text-sm text-fg-3">
                  {data.broken.map((b) => <li key={b.folder}><span className="text-fg">{b.folder}</span> — {b.problems.join(' ; ')}</li>)}
                </ul>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  )
}
