import { useEffect, useRef, useState, type ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { BookOpen, FileSpreadsheet, History, LayoutDashboard, Lightbulb, Menu, Sparkles, UserRound, X } from 'lucide-react'
import { texts } from '../../content/texts'
import { useUserName } from '../../lib/storage'
import { gsap } from '../../motion/gsap'
import { d, ease, stagger } from '../../motion/tokens'
import { IconButton } from '../ui/Button'
import { useApp } from './AppContext'

const NAV = [
  { to: '/', label: texts.nav.grimoire, icon: BookOpen, end: true },
  { to: '/atelier', label: texts.nav.atelier, icon: FileSpreadsheet },
  { to: '/tableau-de-bord', label: texts.nav.dashboard, icon: LayoutDashboard },
  { to: '/historique', label: texts.nav.history, icon: History },
]

function Logo() {
  return (
    <NavLink to="/" className="group flex items-center gap-3" aria-label="MERLIN — retour au grimoire">
      <svg viewBox="0 0 32 32" className="size-8 transition-transform duration-[var(--duration-slow)] ease-[var(--ease-spring)] group-hover:rotate-[20deg]" aria-hidden="true">
        <defs>
          <linearGradient id="logo-g" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#f5dfa5" /><stop offset=".55" stopColor="#a78bfa" /><stop offset="1" stopColor="#5eead4" />
          </linearGradient>
        </defs>
        <path d="M16 2 26 15 16 30 6 15Z" fill="none" stroke="url(#logo-g)" strokeWidth="2" strokeLinejoin="round" />
        <path d="M6 15h20M16 2v28" stroke="url(#logo-g)" strokeWidth="1" opacity=".6" />
      </svg>
      <span className="font-display text-xl tracking-[0.18em] text-parchment">MERLIN</span>
    </NavLink>
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
        mock ? 'border-gold-400/40 text-gold-300 bg-gold-400/10' : 'border-success/40 text-success bg-success/10'}`}
    >
      <span className={`size-1.5 rounded-full ${mock ? 'bg-gold-300' : 'bg-success'} animate-pulse`} aria-hidden="true" />
      {mock ? texts.app.demoBadge : texts.app.fabricBadge}
    </span>
  )
}

function navClass({ isActive }: { isActive: boolean }) {
  return `relative flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition-colors duration-[var(--duration-fast)] ${
    isActive ? 'text-parchment bg-white/8 shadow-[inset_0_0_0_1px_var(--color-line-strong)]' : 'text-mist hover:text-parchment hover:bg-white/5'}`
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
      <a href="#contenu" className="sr-only-focusable fixed left-4 top-4 z-[100] rounded-full bg-gold-300 px-4 py-2 font-semibold text-abyss">
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
            <button onClick={openSuggest} className="hidden sm:inline-flex items-center gap-2 rounded-full px-3.5 py-2 text-sm font-medium text-gold-300 hover:bg-gold-400/10 transition-colors">
              <Lightbulb size={16} aria-hidden="true" />
              {texts.nav.suggest}
            </button>
            <button
              onClick={openUser}
              className="inline-flex items-center gap-2 rounded-full border border-line-strong px-3 py-1.5 text-sm text-mist hover:text-parchment hover:border-violet-400/50 transition-colors"
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
              <button onClick={openSuggest} className="flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-gold-300 hover:bg-gold-400/10">
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
          <span className="font-display text-mist">MERLIN</span> · {texts.app.tagline}
        </p>
        <nav aria-label="Liens secondaires" className="flex gap-5">
          <NavLink to="/a-propos" className="hover:text-parchment">{texts.nav.about}</NavLink>
          <button onClick={openSuggest} className="hover:text-parchment">{texts.nav.suggest}</button>
        </nav>
      </footer>
    </div>
  )
}
