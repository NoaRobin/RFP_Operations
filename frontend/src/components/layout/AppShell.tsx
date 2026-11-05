import { useEffect, useRef, useState, type ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { FileSpreadsheet, History, Mail, Paintbrush, Lightbulb, Menu, Plug, Search, Sparkles, UserRound, X } from 'lucide-react'
import { texts } from '../../content/texts'
import { useUserName } from '../../lib/storage'
import { gsap } from '../../motion/gsap'
import { d, ease, stagger } from '../../motion/tokens'
import { IconButton } from '../ui/Button'
import { AppMark } from '../ui/AppMark'
import { Mascot } from '../../universe/Mascots'
import { UniverseLayer, useUniverse } from '../../universe/UniverseLayer'
import { ORDER, UNIVERSES } from '../../universe/universes'
import { isMac, useApp } from './AppContext'

const MORE = [
  { to: '/qui-contacter', label: texts.nav.contacts, icon: Mail, end: false },
  { to: '/atelier', label: texts.nav.atelier, icon: FileSpreadsheet, end: false },
  { to: '/historique', label: texts.nav.history, icon: History, end: false },
  { to: '/rfpascontente', label: texts.nav.rfpascontente, icon: Paintbrush, end: false },
  { to: '/a-propos', label: texts.nav.about, icon: Sparkles, end: false },
]

function Logo() {
  const u = useUniverse()
  return (
    <NavLink to="/" className="group flex items-center gap-2.5" aria-label={`Merlin — ${texts.nav.home}`}>
      <span className="relative">
        <Mascot universe="merlin" className="size-10 transition-transform duration-[var(--duration-slow)] ease-[var(--ease-spring)] group-hover:-rotate-6 group-hover:scale-110" />
        {u.id !== 'merlin' && u.id !== 'rfp' && (
          <span className="absolute -bottom-1 -right-2 rounded-full border-2 border-fg bg-card p-0.5"><Mascot universe={u.id} className="size-5" /></span>
        )}
      </span>
      <span className="flex flex-col leading-none">
        <span className="whitespace-nowrap font-display text-[1.25rem] font-bold leading-none text-fg">Merlin</span>
        <span className="mt-0.5 hidden whitespace-nowrap font-display text-[0.75rem] font-semibold leading-none text-fg-3 sm:block">l'atelier de l'équipe RFP</span>
      </span>
    </NavLink>
  )
}

/** Les univers (premier étage) : chacun sa couleur, l'univers courant en relief. */
function UniverseTabs() {
  const u = useUniverse()
  return (
    <nav aria-label="Univers" className="ml-2 hidden items-center gap-1.5 lg:flex">
      {ORDER.map((id) => {
        const x = UNIVERSES[id]
        const active = x.id === u.id
        return (
          <NavLink key={id} to={x.home} aria-current={active ? 'page' : undefined}
            className={`flex items-center gap-2 whitespace-nowrap rounded-full border-2 px-3 py-1.5 text-sm font-bold transition-[transform,box-shadow,background] duration-[var(--duration-fast)] ease-[var(--ease-spring)] ${
              active ? 'border-fg text-fg shadow-[2px_2px_0_0_var(--color-fg)]' : 'border-transparent text-fg-2 hover:-translate-y-0.5 hover:bg-fg/5 hover:text-fg'}`}
            style={active ? { background: `color-mix(in srgb, ${x.accent} 38%, white)` } : undefined}>
            {x.id === 'rfp' ? <AppMark className="size-5" /> : <Mascot universe={x.id} className="size-6" />}
            {x.name}
          </NavLink>
        )
      })}
    </nav>
  )
}

/** Second étage : les pages de l'univers courant (Pit Stop a sa propre barre latérale). */
function UniversePages() {
  const u = useUniverse()
  const { pathname } = useLocation()
  if (!u.pages.length || pathname.startsWith('/qvidian')) return null  // le garage QviAPI a sa propre barre latérale
  return (
    <nav aria-label={`Pages de ${u.name}`} className="mx-auto mt-2 flex w-[min(100%-1.5rem,82rem)] gap-1 overflow-x-auto px-1 pb-1">
      {u.pages.map((p) => (
        <NavLink key={p.to} to={p.to} end={p.to === u.home || p.to === '/atelier'}
          className={({ isActive }) => `whitespace-nowrap rounded-full px-3 py-1 text-sm font-bold transition-colors ${isActive ? 'bg-fg text-canvas' : 'text-fg-2 hover:bg-fg/5 hover:text-fg'}`}>
          {p.label}
        </NavLink>
      ))}
    </nav>
  )
}

function PaletteButton() {
  const { openPalette } = useApp()
  return (
    <button
      onClick={openPalette}
      className="group inline-flex items-center gap-2 rounded-full border-2 border-fg bg-card py-1.5 pl-3 pr-1.5 text-sm font-semibold text-fg-2 transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow-[2px_2px_0_0_var(--color-fg)] hover:text-fg"
      aria-keyshortcuts="Meta+K Control+K"
    >
      <Search size={15} aria-hidden="true" />
      <span className="hidden 2xl:inline">{texts.nav.search}</span>
      <kbd className="hidden sm:inline whitespace-nowrap rounded-md border-2 border-fg bg-sun-400 px-1.5 py-0.5 font-mono text-[0.65rem] font-bold text-fg">{isMac() ? '⌘K' : 'Ctrl K'}</kbd>
    </button>
  )
}

function FabricPill() {
  const { health, fabric, openFabric } = useApp()
  if (!health) return null
  const live = health.data_mode === 'fabric'
  return (
    <button
      onClick={openFabric}
      title={live ? texts.fabric.connected(fabric?.user ?? '') : texts.app.demoBadgeHint}
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border-2 border-fg px-3 py-1.5 text-xs font-bold transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow-[2px_2px_0_0_var(--color-fg)] ${
        live ? 'bg-mint-400 text-fg' : 'bg-sun-400 text-fg'}`}
    >
      <span className={`size-2 rounded-full border border-fg ${live ? 'bg-white' : 'bg-bubble-400'} animate-pulse`} aria-hidden="true" />
      {live ? <span className="hidden md:inline">{texts.app.fabricBadge}</span> : <><Plug size={13} aria-hidden="true" /><span>Fabric</span></>}
    </button>
  )
}

function navClass({ isActive }: { isActive: boolean }) {
  return `relative flex items-center gap-2 whitespace-nowrap rounded-full border-2 px-3 py-1.5 text-sm font-bold transition-[background,transform,box-shadow] duration-[var(--duration-fast)] ease-[var(--ease-spring)] ${
    isActive ? 'border-fg bg-sun-400 text-fg shadow-[2px_2px_0_0_var(--color-fg)]' : 'border-transparent text-fg-2 hover:text-fg hover:bg-fg/5 hover:-translate-y-0.5'}`
}

export function AppShell({ children }: { children: ReactNode }) {
  const { openSuggest, openUser } = useApp()
  const name = useUserName()
  const [menu, setMenu] = useState(false)
  const location = useLocation()
  const mobileRef = useRef<HTMLDivElement>(null)

  useEffect(() => setMenu(false), [location.pathname])
  useEffect(() => {
    if (!menu || !mobileRef.current) return
    gsap.fromTo(mobileRef.current.querySelectorAll('a,button'), { opacity: 0, y: 12 }, { opacity: 1, y: 0, stagger: stagger.base, duration: d('base'), ease: ease.out })
  }, [menu])

  return (
    <div className="relative min-h-dvh flex flex-col">
      <UniverseLayer />
      <a href="#contenu" className="sr-only-focusable fixed left-4 top-4 z-[100] rounded-full bg-sun-400 px-4 py-2 font-semibold text-on-accent">
        {texts.app.skipToContent}
      </a>
      <header className="sticky top-0 z-50">
        <div className="mx-auto mt-3 flex w-[min(100%-1.5rem,82rem)] items-center gap-2 sm:gap-4 rounded-full glass px-3 py-2.5 sm:px-5">
          <Logo />
          <UniverseTabs />
          <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
            <FabricPill />
            <PaletteButton />
            <button
              onClick={openUser}
              className="hidden sm:inline-flex items-center gap-2 rounded-full border-2 border-fg bg-card px-3 py-1.5 text-sm font-semibold text-fg-2 hover:text-fg hover:bg-magic-400/20 transition-colors"
              title={name ? texts.user.rename : texts.user.introduce}
            >
              <UserRound size={16} aria-hidden="true" />
              <span className="max-w-[8rem] truncate">{name || texts.user.introduce}</span>
            </button>
            <IconButton label={menu ? texts.nav.close : texts.nav.menu} className="lg:hidden" onClick={() => setMenu((m) => !m)} aria-expanded={menu}>
              {menu ? <X size={20} /> : <Menu size={20} />}
            </IconButton>
          </div>
        </div>
        <UniversePages />
        {menu && (
          <div ref={mobileRef} className="lg:hidden mx-auto mt-2 w-[min(100%-1.5rem,82rem)] glass rounded-[var(--radius-card)] p-3">
            <nav aria-label="Navigation mobile" className="flex flex-col gap-1">
              {ORDER.map((id) => (
                <div key={id} className="flex flex-col gap-0.5">
                  <NavLink to={UNIVERSES[id].home} end className={navClass}>{UNIVERSES[id].name}</NavLink>
                  {UNIVERSES[id].pages.filter((p) => p.to !== UNIVERSES[id].home).map((p) => (
                    <NavLink key={p.to} to={p.to} end className={({ isActive }) => `ml-6 rounded-full px-3 py-1 text-sm font-semibold ${isActive ? 'bg-fg text-canvas' : 'text-fg-2'}`}>{p.label}</NavLink>
                  ))}
                </div>
              ))}
              <button onClick={openSuggest} className="flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-sun-300 hover:bg-sun-400/10">
                <Lightbulb size={16} aria-hidden="true" />
                {texts.nav.suggest}
              </button>
            </nav>
          </div>
        )}
      </header>
      <main id="contenu" tabIndex={-1} className="relative flex-1 outline-none">
        {children}
      </main>
      <footer className="mx-auto w-[min(100%-2rem,82rem)] border-t-2 border-dashed border-fg/25 py-8 mt-16 flex flex-wrap items-center justify-between gap-4 text-sm text-fg-3">
        <p>
          <span className="font-display font-bold text-fg">{texts.app.name}</span> · <span className="font-bold text-magic-300">{texts.app.hashtag}</span> · {texts.app.tagline}
        </p>
        <nav aria-label="Liens secondaires" className="flex flex-wrap gap-5 font-semibold">
          {MORE.map(({ to, label }) => <NavLink key={to} to={to} className="hover:text-fg">{label}</NavLink>)}
          <button onClick={openSuggest} className="hover:text-fg">{texts.nav.suggest}</button>
        </nav>
      </footer>
    </div>
  )
}
