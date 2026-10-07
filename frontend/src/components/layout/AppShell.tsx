import { useEffect, useRef, useState, type ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { BookOpen, FileSpreadsheet, History, LayoutDashboard, Lightbulb, Menu, Search, Sparkles, UserRound, X } from 'lucide-react'
import { texts } from '../../content/texts'
import { useUserName } from '../../lib/storage'
import { gsap } from '../../motion/gsap'
import { d, ease, stagger } from '../../motion/tokens'
import { IconButton } from '../ui/Button'
import { MeridianMark } from '../ui/MeridianMark'
import { isMac, useApp } from './AppContext'

const NAV = [
  { to: '/', label: texts.nav.library, icon: BookOpen, end: true },
  { to: '/atelier', label: texts.nav.atelier, icon: FileSpreadsheet },
  { to: '/tableau-de-bord', label: texts.nav.dashboard, icon: LayoutDashboard },
  { to: '/historique', label: texts.nav.history, icon: History },
]

function Logo() {
  return (
    <NavLink to="/" className="group flex items-center gap-3" aria-label={`${texts.app.name} — ${texts.nav.library}`}>
      <MeridianMark className="size-8 transition-transform duration-[var(--duration-slow)] ease-[var(--ease-spring)] group-hover:rotate-[24deg]" />
      <span className="flex flex-col leading-none">
        <span className="font-display text-[1.35rem] tracking-[0.16em] text-ivory">{texts.app.name}</span>
        <span className="mt-0.5 hidden font-mono text-[0.55rem] uppercase tracking-[0.32em] text-haze xl:block">{texts.app.suite}</span>
      </span>
    </NavLink>
  )
}

function PaletteButton() {
  const { openPalette } = useApp()
  return (
    <button
      onClick={openPalette}
      className="group inline-flex items-center gap-2 rounded-full border border-line-strong bg-abyss/40 py-1.5 pl-3 pr-1.5 text-sm text-mist transition-colors hover:border-champagne-400/50 hover:text-ivory"
      aria-keyshortcuts="Meta+K Control+K"
    >
      <Search size={15} aria-hidden="true" />
      <span className="hidden sm:inline">{texts.nav.search}</span>
      <kbd className="rounded-md border border-line px-1.5 py-0.5 font-mono text-[0.65rem] text-haze group-hover:text-champagne-300">{isMac() ? '⌘K' : 'Ctrl K'}</kbd>
    </button>
  )
}

function DataModeBadge() {
  const { health } = useApp()
  if (!health) return null
  const mock = health.data_mode === 'mock'
  return (
    <span
      title={mock ? texts.app.demoBadgeHint : undefined}
      className={`hidden md:inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium ${
        mock ? 'border-champagne-400/40 text-champagne-300 bg-champagne-400/10' : 'border-success/40 text-success bg-success/10'}`}
    >
      <span className={`size-1.5 rounded-full ${mock ? 'bg-champagne-300' : 'bg-success'} animate-pulse`} aria-hidden="true" />
      {mock ? texts.app.demoBadge : texts.app.fabricBadge}
    </span>
  )
}

function navClass({ isActive }: { isActive: boolean }) {
  return `relative flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition-colors duration-[var(--duration-fast)] ${
    isActive ? 'text-ivory bg-white/8 shadow-[inset_0_0_0_1px_var(--color-line-strong)]' : 'text-mist hover:text-ivory hover:bg-white/5'}`
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
      <a href="#contenu" className="sr-only-focusable fixed left-4 top-4 z-[100] rounded-full bg-champagne-300 px-4 py-2 font-semibold text-abyss">
        {texts.app.skipToContent}
      </a>
      <header className="sticky top-0 z-50">
        <div className="mx-auto mt-3 flex w-[min(100%-1.5rem,82rem)] items-center gap-4 rounded-full glass px-4 py-2.5 sm:px-5">
          <Logo />
          <nav aria-label="Navigation principale" className="ml-4 hidden lg:flex items-center gap-1">
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <NavLink key={to} to={to} end={end} className={navClass}>
                <Icon size={16} aria-hidden="true" />
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <DataModeBadge />
            <PaletteButton />
            <IconButton label={texts.nav.suggest} onClick={openSuggest} className="hidden sm:inline-grid !text-champagne-300">
              <Lightbulb size={18} />
            </IconButton>
            <button
              onClick={openUser}
              className="inline-flex items-center gap-2 rounded-full border border-line-strong px-3 py-1.5 text-sm text-mist hover:text-ivory hover:border-steel-400/50 transition-colors"
              title={name ? texts.user.rename : texts.user.introduce}
            >
              <UserRound size={16} aria-hidden="true" />
              <span className="max-w-[9rem] truncate">{name || texts.user.introduce}</span>
            </button>
            <IconButton label={menu ? texts.nav.close : texts.nav.menu} className="lg:hidden" onClick={() => setMenu((m) => !m)} aria-expanded={menu}>
              {menu ? <X size={20} /> : <Menu size={20} />}
            </IconButton>
          </div>
        </div>
        {menu && (
          <div ref={mobileRef} className="lg:hidden mx-auto mt-2 w-[min(100%-1.5rem,82rem)] glass rounded-[var(--radius-card)] p-3">
            <nav aria-label="Navigation mobile" className="flex flex-col gap-1">
              {[...NAV, { to: '/a-propos', label: texts.nav.about, icon: Sparkles, end: false }].map(({ to, label, icon: Icon, end }) => (
                <NavLink key={to} to={to} end={end} className={navClass}>
                  <Icon size={16} aria-hidden="true" />
                  {label}
                </NavLink>
              ))}
              <button onClick={openSuggest} className="flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-champagne-300 hover:bg-champagne-400/10">
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
      <footer className="mx-auto w-[min(100%-2rem,82rem)] border-t hairline py-8 mt-16 flex flex-wrap items-center justify-between gap-4 text-sm text-haze">
        <p>
          <span className="font-display text-mist">{texts.app.name}</span> · {texts.app.tagline}
        </p>
        <nav aria-label="Liens secondaires" className="flex gap-5">
          <NavLink to="/a-propos" className="hover:text-ivory">{texts.nav.about}</NavLink>
          <button onClick={openSuggest} className="hover:text-ivory">{texts.nav.suggest}</button>
        </nav>
      </footer>
    </div>
  )
}
