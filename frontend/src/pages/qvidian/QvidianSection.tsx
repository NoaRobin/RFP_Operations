/**
 * Section Qvidian : une partie de l'app à part entière, avec sa propre navigation latérale (explorer, qualité, agir,
 * système), une recherche globale (touche « / »), la sélection gardée d'une vue à l'autre et l'état de la connexion.
 */
import { useEffect, useRef, useState } from 'react'
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { Activity, Bot, BrainCircuit, CalendarClock, Copy, Cpu, Download, FolderTree, Gauge, HeartPulse, History, Library, LogIn, MessagesSquare, PenSquare, Plug, RefreshCw, Search, ShieldCheck, Sparkles, Tags, X } from 'lucide-react'
import { Button } from '../../components/ui/Button'
import { ErrorState, Loading } from '../../components/ui/States'
import { useToast } from '../../components/ui/Toast'
import { MemoryView } from './views/MemoryView'
import { DuplicatesView, FreshnessView, QuestionsView } from './views/WorkshopViews'
import { texts } from '../../content/texts'
import { api } from '../../lib/api'
import { gsap, useGSAP } from '../../motion/gsap'
import { d, ease, prefersReducedMotion } from '../../motion/tokens'
import { QvidianProvider, useQvidian } from './context'
import { AiView, AnswersView, ConnectionView, HealthView, JournalView } from './views/Quality'
import { ApiView } from './views/ApiView'
import { Cockpit } from './views/Cockpit'
import { ContentView } from './views/ContentView'
import { EditView } from './views/EditView'
import { LibraryView } from './views/LibraryView'
import { SearchView } from './views/SearchView'

const Q = texts.qvidian
const NAV: { group: string; items: { to: string; key: string; icon: typeof Gauge; external?: boolean }[] }[] = [
  { group: 'pilot', items: [{ to: '', key: 'accueil', icon: Gauge }, { to: 'memoire', key: 'memoire', icon: BrainCircuit }] },
  { group: 'find', items: [{ to: 'recherche', key: 'recherche', icon: Search }, { to: 'bibliotheque', key: 'bibliotheque', icon: FolderTree },
    { to: 'questions', key: 'questions', icon: MessagesSquare }, { to: 'reponses', key: 'reponses', icon: Sparkles }] },
  { group: 'care', items: [{ to: 'sante', key: 'sante', icon: HeartPulse }, { to: 'fraicheur', key: 'fraicheur', icon: CalendarClock },
    { to: 'doublons', key: 'doublons', icon: Copy }, { to: 'ia', key: 'ia', icon: Bot }] },
  { group: 'act', items: [{ to: 'modifier', key: 'modifier', icon: PenSquare }, { to: 'journal', key: 'journal', icon: History },
    { to: '/merge-codes', key: 'mergecodes', icon: Tags, external: true }] },
  { group: 'system', items: [{ to: 'api', key: 'api', icon: Cpu }, { to: 'connexion', key: 'connexion', icon: Plug }] },
]
const LEGACY: Record<string, string> = { apercu: '', carte: 'sante', bibliotheque: 'bibliotheque', reponses: 'reponses', ia: 'ia', modifier: 'modifier', connexion: 'connexion' }

function Sidebar() {
  const { status, audit, selected, clear } = useQvidian()
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (e.key !== '/' || e.metaKey || e.ctrlKey || t.closest('input, textarea, select, [contenteditable="true"]')) return
      e.preventDefault()
      input.current?.focus()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  const badge: Record<string, number | undefined> = { sante: audit?.with_issues || undefined, modifier: selected.size || undefined, ia: selected.size || undefined }
  return (
    <aside className="flex flex-col gap-4 lg:sticky lg:top-24 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto" aria-label={Q.section} data-lenis-prevent>
      <div className="rounded-[var(--radius-card)] border-[2.5px] border-fg bg-card p-4 shadow-[4px_4px_0_0_var(--color-fg)]">
        <p className="flex items-center gap-2 font-display text-2xl font-semibold tracking-tight"><Library size={20} className="text-magic-500" aria-hidden="true" />QviAPI</p>
        <p className="mt-1 text-xs font-semibold text-fg-2">{texts.qviapi.lead}</p>
        {status && (
          <p className={`mt-3 inline-flex items-center gap-1.5 rounded-full border-2 border-fg px-2.5 py-0.5 text-xs font-bold ${status.mode === 'demo' ? 'bg-sun-400' : status.connected ? 'bg-mint-400' : 'bg-[#ffd6dc]'}`}>
            <span className={`size-2 rounded-full ${status.connected ? 'bg-fg' : 'bg-fg/40'}`} aria-hidden="true" />
            {Q.mode[status.mode]}{status.mode === 'qvidian' ? ` · ${status.connected ? Q.connectedAs(status.user) : Q.notConnected}` : ''}
          </p>
        )}
        <form className="relative mt-3" role="search" onSubmit={(e) => { e.preventDefault(); navigate(`/qvidian/recherche?q=${encodeURIComponent(q)}`) }}>
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-3" aria-hidden="true" />
          <input ref={input} value={q} onChange={(e) => setQ(e.target.value)} placeholder={Q.quickSearch} aria-label={Q.quickSearch}
            className="h-10 w-full rounded-xl border-2 border-fg bg-field pl-9 pr-8 text-sm font-semibold placeholder:font-normal placeholder:text-fg-3 focus:shadow-[3px_3px_0_0_var(--color-magic-500)] focus:outline-none" />
          <kbd className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded border border-fg/30 px-1 text-[0.65rem] font-bold text-fg-3">{Q.quickSearchKey}</kbd>
        </form>
      </div>
      <nav className="flex gap-4 overflow-x-auto rounded-[var(--radius-card)] border-2 border-fg bg-card p-3 lg:flex-col lg:overflow-visible" aria-label={Q.tabsLabel}>
        {NAV.map((g) => (
          <div key={g.group} className="flex shrink-0 gap-1 lg:flex-col">
            <p className="hidden px-2 pb-1 text-[0.65rem] font-bold uppercase tracking-widest text-fg-3 lg:block">{Q.navGroups[g.group]}</p>
            {g.items.map((it) => {
              const Icon = it.icon
              return (
                <NavLink key={it.key} to={it.external ? it.to : `/qvidian${it.to ? `/${it.to}` : ''}`} end={it.to === ''}
                  className={({ isActive }) => `inline-flex shrink-0 items-center gap-2 rounded-xl px-3 py-2 text-sm font-bold transition-colors ${isActive ? 'bg-fg text-canvas' : 'hover:bg-card-2'}`}>
                  <Icon size={16} aria-hidden="true" />
                  <span>{Q.nav[it.key]}</span>
                  {badge[it.key] ? <span className="ml-auto rounded-full bg-sun-400 px-1.5 text-[0.7rem] tabular-nums text-fg">{badge[it.key]}</span> : null}
                </NavLink>
              )
            })}
          </div>
        ))}
      </nav>
      {selected.size > 0 && (
        <div className="rounded-[var(--radius-card)] border-[2.5px] border-fg bg-sun-400/40 p-3" role="region" aria-label={Q.selected(selected.size)}>
          <p className="flex items-center gap-2 font-display font-semibold"><Activity size={15} aria-hidden="true" />{Q.selected(selected.size)}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button size="sm" variant="primary" onClick={() => navigate('/qvidian/modifier')} icon={<PenSquare size={14} />}>{Q.trayEdit}</Button>
            <Button size="sm" onClick={() => navigate('/qvidian/ia')} icon={<Bot size={14} />}>{Q.trayAi}</Button>
            <Button size="sm" onClick={async () => {
              const blob = await api.qvidian.exportSelection([...selected])
              const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'Selection_Qvidian.xlsx'; a.click(); URL.revokeObjectURL(a.href)
            }} icon={<Download size={14} />}>{texts.qviapi.exportSel}</Button>
            <button onClick={clear} aria-label={Q.unselect} className="rounded-full border-2 border-fg/30 p-1.5 hover:border-fg"><X size={14} /></button>
          </div>
        </div>
      )}
    </aside>
  )
}

function StatusBar() {
  const { status, sync } = useQvidian()
  const toast = useToast()
  if (!status) return null
  const connected = status.mode === 'qvidian' && status.connected
  const sso = async () => {
    try { window.location.href = (await api.qvidian.ssoStart()).url } catch (e) {
      toast('error', (e as Error).message)
    }
  }
  const snap = status.snapshot
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-2xl border-[2.5px] border-fg bg-card px-3 py-2 shadow-[3px_3px_0_0_var(--color-fg)]">
      <span className="inline-flex items-center gap-1 text-xs font-bold text-fg-2"><ShieldCheck size={13} aria-hidden="true" />{status.write_enabled ? Q.writeLocked : Q.readOnly}</span>
      <span className="text-xs font-semibold text-fg-3">
        {snap.synced_at ? Q.lastSync(snap.synced_at.replace('T', ' ').slice(0, 16), snap.count ?? '0') : Q.noSync}
        {status.sync.result?.mode ? ` · ${Q.lastSyncCard(status.sync.result.mode, status.sync.result.seconds ?? 0)}` : ''}
      </span>
      {status.sync.error && <span role="alert" className="text-xs font-bold text-danger">{status.sync.error.message}</span>}
      <span className="ml-auto flex gap-2">
        {!connected && status.mode !== 'off' && status.mode !== 'demo' && !status.credentials && <Button size="sm" variant="primary" onClick={sso} icon={<LogIn size={14} />}>{Q.sso}</Button>}
        {status.connect_error && <span role="alert" className="text-xs font-bold text-danger">{status.connect_error}</span>}
        <Button size="sm" onClick={() => sync('auto')} loading={status.sync.running} disabled={status.sync.running || status.mode === 'off'} icon={<RefreshCw size={14} />}>
          {status.sync.running ? `${Q.syncing} ${status.sync.message}` : Q.syncAuto}
        </Button>
      </span>
    </div>
  )
}

function Body() {
  const { status, error, reload } = useQvidian()
  const [params, setParams] = useSearchParams()
  const toast = useToast()
  const location = useLocation()
  const root = useRef<HTMLDivElement>(null)
  useGSAP(() => {
    if (prefersReducedMotion()) return
    gsap.from('[data-enter]', { y: 14, opacity: 0, stagger: 0.04, duration: d('base'), ease: ease.out })
  }, { scope: root, dependencies: [location.pathname, !!status] })

  useEffect(() => {
    const sso = params.get('sso')
    if (!sso) return
    toast(sso === 'ok' ? 'success' : 'error', sso === 'ok' ? Q.ssoOk : Q.ssoFail, sso === 'ok' ? undefined : params.get('raison') ?? undefined)
    const next = new URLSearchParams(params)
    next.delete('raison'); next.delete('sso')
    setParams(next, { replace: true })
    void reload()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const legacy = params.get('onglet')
  if (legacy && legacy in LEGACY) return <Navigate to={`/qvidian/${LEGACY[legacy]}`} replace />

  return (
    <div ref={root} className="flex min-w-0 flex-col gap-5">
      <StatusBar />
      {error && <ErrorState error={error} onRetry={reload} />}
      {!status && !error && <Loading />}
      {status && (
        <Routes>
          <Route index element={<Cockpit />} />
          <Route path="memoire" element={<MemoryView />} />
          <Route path="questions" element={<QuestionsView />} />
          <Route path="fraicheur" element={<FreshnessView />} />
          <Route path="doublons" element={<DuplicatesView />} />
          <Route path="recherche" element={<SearchView />} />
          <Route path="bibliotheque" element={<LibraryView />} />
          <Route path="contenu/:id" element={<ContentView />} />
          <Route path="reponses" element={<AnswersView />} />
          <Route path="sante" element={<HealthView />} />
          <Route path="ia" element={<AiView />} />
          <Route path="modifier" element={<EditView />} />
          <Route path="journal" element={<JournalView />} />
          <Route path="api" element={<ApiView />} />
          <Route path="connexion" element={<ConnectionView />} />
          <Route path="*" element={<Navigate to="/qvidian" replace />} />
        </Routes>
      )}
    </div>
  )
}

export default function QvidianSection() {
  // QviAPI : la salle des machines passe au sombre (styles/qviapi.css) le temps d'y être
  useEffect(() => {
    document.documentElement.dataset.section = 'qviapi'
    return () => { delete document.documentElement.dataset.section }
  }, [])
  return (
    <QvidianProvider>
      <div className="qv mx-auto grid w-[min(100%-2rem,112rem)] gap-6 pb-24 pt-8 lg:grid-cols-[16rem_minmax(0,1fr)]">
        <Sidebar />
        <Body />
      </div>
    </QvidianProvider>
  )
}
