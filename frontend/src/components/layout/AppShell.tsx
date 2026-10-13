import { useEffect, useRef, useState, type ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { Activity, BookOpen, CalendarCheck, FileDown, FileQuestion, FileSpreadsheet, History, LayoutDashboard, Lightbulb, Menu, Plug, Search, Sparkles, Tags, UserRound, X } from 'lucide-react'
import { texts } from '../../content/texts'
import { useUserName } from '../../lib/storage'
import { gsap } from '../../motion/gsap'
import { d, ease, stagger } from '../../motion/tokens'
import { IconButton } from '../ui/Button'
import { AppMark } from '../ui/AppMark'
import { isMac, useApp } from './AppContext'

const NAV = [
  { to: '/rfi', label: texts.nav.rfi, icon: FileQuestion, end: false },
  { to: '/documents', label: texts.nav.fundshop, icon: FileDown, end: false },
  { to: '/omni', label: texts.nav.omni, icon: CalendarCheck, end: false },
  { to: '/merge-codes', label: texts.nav.merge, icon: Tags, end: false },
  { to: '/suivi-activite', label: texts.nav.suivi, icon: Activity, end: false },
  { to: '/sorts', label: texts.nav.library, icon: BookOpen, end: false },
  { to: '/tableau-de-bord', label: texts.nav.dashboard, icon: LayoutDashboard, end: false },
]
const MORE = [
  { to: '/atelier', label: texts.nav.atelier, icon: FileSpreadsheet, end: false },
  { to: '/historique', label: texts.nav.history, icon: History, end: false },
  { to: '/a-propos', label: texts.nav.about, icon: Sparkles, end: false },
]

function Logo() {
  return (
    <NavLink to="/" className="group flex items-center gap-3" aria-label={`${texts.app.name} — ${texts.nav.home}`}>
      <AppMark className="size-9 transition-transform duration-[var(--duration-slow)] ease-[var(--ease-spring)] group-hover:-rotate-12 group-hover:scale-110" />
      <span className="flex flex-col leading-none">
        <span className="whitespace-nowrap font-display text-[1.05rem] font-bold leading-none text-fg sm:text-[1.2rem]">{texts.app.short}</span>
        <span className="mt-0.5 whitespace-nowrap font-display text-[0.8rem] font-semibold leading-none text-bubble-300">{texts.app.sub}</span>
      </span>
    </NavLink>
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
      <a href="#contenu" className="sr-only-focusable fixed left-4 top-4 z-[100] rounded-full bg-sun-400 px-4 py-2 font-semibold text-on-accent">
        {texts.app.skipToContent}
      </a>
      <header className="sticky top-0 z-50">
        <div className="mx-auto mt-3 flex w-[min(100%-1.5rem,82rem)] items-center gap-2 sm:gap-4 rounded-full glass px-3 py-2.5 sm:px-5">
          <Logo />
          <nav aria-label="Navigation principale" className="ml-2 hidden xl:flex items-center gap-1">
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <NavLink key={to} to={to} end={end} className={navClass}>
                <Icon size={16} aria-hidden="true" />
                {label}
              </NavLink>
            ))}
          </nav>
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
            <IconButton label={menu ? texts.nav.close : texts.nav.menu} className="xl:hidden" onClick={() => setMenu((m) => !m)} aria-expanded={menu}>
              {menu ? <X size={20} /> : <Menu size={20} />}
            </IconButton>
          </div>
        </div>
        {menu && (
          <div ref={mobileRef} className="xl:hidden mx-auto mt-2 w-[min(100%-1.5rem,82rem)] glass rounded-[var(--radius-card)] p-3">
            <nav aria-label="Navigation mobile" className="flex flex-col gap-1">
              {[...NAV, ...MORE].map(({ to, label, icon: Icon, end }) => (
                <NavLink key={to} to={to} end={end} className={navClass}>
                  <Icon size={16} aria-hidden="true" />
                  {label}
                </NavLink>
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
