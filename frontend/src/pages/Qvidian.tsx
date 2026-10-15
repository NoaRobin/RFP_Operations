/**
 * Fenêtre Qvidian : connexion (identifiant, clé d'API ou SSO), instantané local de la bibliothèque, carte des erreurs,
 * analyse IA par Copilot, réponse type agrégée (utilisations × récence), modifications en masse protégées par mot de passe,
 * import des projets comme anciens RFI. Lecture seule par défaut.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Activity, Bot, Gauge, Library, LogIn, LogOut, Map as MapIcon, PenSquare, Plug, RefreshCw, Search, ShieldCheck, Sparkles, Upload, X } from 'lucide-react'
import { AiPanel } from '../components/qvidian/AiPanel'
import { BulkPanel } from '../components/qvidian/BulkPanel'
import { ContentList } from '../components/qvidian/ContentList'
import { ErrorMap, type MapFilter } from '../components/qvidian/ErrorMap'
import { Button } from '../components/ui/Button'
import { Field, Select, Switch, TextInput } from '../components/ui/Field'
import { ErrorState, Loading } from '../components/ui/States'
import { useToast } from '../components/ui/Toast'
import { texts } from '../content/texts'
import { api, ApiError } from '../lib/api'
import type { QvidianAudit, QvidianJournalEntry, QvidianStatus, QvidianSuggest } from '../lib/types'
import { gsap, useGSAP } from '../motion/gsap'
import { d, ease, prefersReducedMotion } from '../motion/tokens'

const Q = texts.qvidian
type Tab = 'apercu' | 'carte' | 'bibliotheque' | 'reponses' | 'ia' | 'modifier' | 'connexion'
const TABS: Tab[] = ['apercu', 'carte', 'bibliotheque', 'reponses', 'ia', 'modifier', 'connexion']
const PAGE = 60

function ConnectionPanel({ status, onChange }: { status: QvidianStatus; onChange: (s: QvidianStatus) => void }) {
  const toast = useToast()
  const [user, setUser] = useState('')
  const [password, setPassword] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [busy, setBusy] = useState(false)
  const fail = (e: unknown) => toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
  const connect = async () => {
    setBusy(true)
    try { onChange(await api.qvidian.connect(user, password, apiKey)); setPassword(''); setApiKey('') } catch (e) { fail(e) } finally { setBusy(false) }
  }
  const sso = async () => {
    try { window.location.href = (await api.qvidian.ssoStart()).url } catch (e) { fail(e) }
  }
  const sync = async () => {
    try { await api.qvidian.sync(); onChange(await api.qvidian.status()) } catch (e) { fail(e) }
  }
  const synced = status.snapshot.synced_at
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className={`rounded-full border-[2.5px] border-fg px-3 py-1 text-sm font-bold ${status.mode === 'demo' ? 'bg-sun-400' : status.mode === 'qvidian' ? 'bg-mint-400' : 'bg-card-3'}`}>
          {Q.mode[status.mode]}{status.mode === 'qvidian' ? ` · ${status.connected ? Q.connectedAs(status.user) : Q.notConnected}` : ''}
        </span>
        <span className="inline-flex items-center gap-1.5 rounded-full border-2 border-fg/40 px-3 py-1 text-xs font-bold">
          <ShieldCheck size={14} aria-hidden="true" />{Q.readOnly} · {status.write_enabled ? Q.writeLocked : Q.writeOff}
        </span>
        <span className="text-sm font-semibold text-fg-2">
          {synced ? Q.lastSync(synced.replace('T', ' ').slice(0, 16), status.snapshot.count ?? '0') : Q.noSync}
        </span>
        <span className="ml-auto flex flex-wrap gap-2">
          <Button size="sm" onClick={sync} loading={status.sync.running} disabled={status.sync.running || status.mode === 'off'} icon={<RefreshCw size={15} />}>
            {status.sync.running ? `${Q.syncing} ${status.sync.message}` : Q.sync}
          </Button>
          {status.mode === 'qvidian' && status.connected && !status.credentials && (
            <Button size="sm" variant="ghost" onClick={async () => onChange(await api.qvidian.disconnect())} icon={<LogOut size={15} />}>{Q.disconnect}</Button>
          )}
        </span>
      </div>
      {status.sync.error && <p role="alert" className="text-sm font-semibold text-danger">{status.sync.error.message} — {status.sync.error.hint}</p>}
      {status.sync.result && !status.sync.running && (
        <p className="text-sm font-semibold text-fg-2">{Q.syncDone(status.sync.result.contents)}{status.sync.result.problems.length ? ` · ${status.sync.result.problems.join(' · ')}` : ''}</p>
      )}
      {status.mode !== 'off' && !(status.mode === 'qvidian' && status.connected) && (
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border-[2.5px] border-fg bg-sun-400/30 p-3">
          <Button variant="primary" onClick={sso} disabled={!status.sso} icon={<LogIn size={17} />}>{Q.sso}</Button>
          <p className="min-w-[16rem] flex-1 text-sm font-semibold text-fg-2">{status.sso_suffix ? Q.ssoHint : Q.ssoNoSuffix}</p>
          {status.last_sso_error && <p role="alert" className="w-full text-sm font-bold text-danger">{Q.ssoLast} {status.last_sso_error}</p>}
        </div>
      )}
      {status.mode !== 'off' && !(status.mode === 'qvidian' && status.connected) && (
        <details className="rounded-2xl border-2 border-fg/20 bg-card p-3">
          <summary className="cursor-pointer font-display font-semibold">{Q.connectOther}</summary>
          <p className="mt-1 text-xs font-semibold text-fg-3">{Q.connectHint}</p>
          <form className="mt-3 grid gap-3 sm:grid-cols-4" onSubmit={(e) => { e.preventDefault(); void connect() }}>
            <Field label={Q.user}>{({ id }) => <TextInput id={id} autoComplete="username" value={user} onChange={(e) => setUser(e.target.value)} />}</Field>
            <Field label={Q.password}>{({ id }) => <TextInput id={id} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />}</Field>
            <Field label={Q.apiKey}>{({ id }) => <TextInput id={id} type="password" autoComplete="off" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />}</Field>
            <div className="flex items-end gap-2">
              <Button type="submit" variant="primary" disabled={!user || (!password && !apiKey) || busy} loading={busy} icon={<LogIn size={16} />}>{Q.connect}</Button>
            </div>
          </form>
        </details>
      )}
    </section>
  )
}

function SuggestPanel({ halfLife }: { halfLife: number }) {
  const [q, setQ] = useState('')
  const [res, setRes] = useState<QvidianSuggest | null>(null)
  const [busy, setBusy] = useState(false)
  const go = async () => {
    if (!q.trim()) return
    setBusy(true)
    try { setRes(await api.qvidian.suggest(q)) } finally { setBusy(false) }
  }
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm font-semibold text-fg-2">{Q.suggestLead}</p>
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void go() }}>
        <TextInput aria-label={Q.suggestPlaceholder} value={q} onChange={(e) => setQ(e.target.value)} placeholder={Q.suggestPlaceholder} />
        <Button type="submit" loading={busy} icon={<Search size={16} />}>{Q.suggestGo}</Button>
      </form>
      <p className="text-xs font-semibold text-fg-3">{Q.halfLife(halfLife)}</p>
      {res && res.choices.length === 0 && <p className="text-sm font-semibold">{Q.suggestNone}</p>}
      {res?.choices.map((c, i) => (
        <article key={i} className={`rounded-2xl border-2 p-3 ${i === 0 ? 'border-fg bg-sun-400/20' : 'border-fg/25 bg-card'}`}>
          <div className="flex items-center gap-2">
            <span className="h-2 flex-1 overflow-hidden rounded-full border border-fg/40 bg-card-2"><span className="block h-full bg-magic-400" style={{ width: `${Math.max(4, Math.round(c.share * 100))}%` }} /></span>
            <span className="text-xs font-bold tabular-nums">{Math.round(c.share * 100)} %</span>
          </div>
          <p className="mt-2 whitespace-pre-line text-sm font-semibold">{c.value}</p>
          <p className="mt-1 text-xs font-semibold text-fg-2">{c.why} · contenus {c.contents.map((x) => `#${x}`).join(', ')}</p>
        </article>
      ))}
    </div>
  )
}

function ProjectsPanel() {
  const toast = useToast()
  const [limit, setLimit] = useState(20)
  const [busy, setBusy] = useState(false)
  const go = async () => {
    setBusy(true)
    try {
      const r = await api.qvidian.importProjects(limit)
      toast('success', Q.projectsDone(r.imported, r.projects))
    } catch (e) {
      toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
    } finally { setBusy(false) }
  }
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm font-semibold text-fg-2">{Q.projectsLead}</p>
      <Field label="Nombre de projets">
        {({ id }) => (
          <Select id={id} value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
            {[10, 20, 50, 100].map((n) => <option key={n} value={n}>{n}</option>)}
          </Select>
        )}
      </Field>
      <Button onClick={go} loading={busy} disabled={busy} icon={<Upload size={16} />}>{Q.projectsGo(limit)}</Button>
    </div>
  )
}

const SEV_BAR: Record<string, string> = { haute: 'bg-bubble-400', moyenne: 'bg-sun-400', basse: 'bg-mint-400' }

/** Santé de la bibliothèque : part des contenus sans défaut, pondérée par la gravité. */
function health(audit: QvidianAudit): number {
  if (!audit.contents) return 100
  const weight: Record<string, number> = { haute: 1, moyenne: 0.5, basse: 0.15 }
  const penalty = audit.items.reduce((sum, it) => sum + Math.min(1, it.issues.reduce((m, i) => Math.max(m, weight[i.severity] ?? 0.3), 0)), 0)
  return Math.round(100 * (1 - penalty / audit.contents))
}

function Overview({ audit, status, onGo }: { audit: QvidianAudit; status: QvidianStatus; onGo: (tab: Tab, f?: MapFilter) => void }) {
  const score = health(audit)
  const tone = score >= 80 ? 'bg-mint-400' : score >= 60 ? 'bg-sun-400' : 'bg-bubble-400'
  const max = Math.max(1, ...audit.categories.map((c) => c.count))
  const worst = [...audit.groups].sort((a, b) => b.with_issues / Math.max(b.total, 1) - a.with_issues / Math.max(a.total, 1)).slice(0, 5)
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
      <div className="flex flex-col gap-5">
        <div className="flex items-center gap-5 rounded-[var(--radius-card)] border-[2.5px] border-fg bg-card p-5 shadow-[var(--shadow-pop)]">
          <div className={`grid size-28 shrink-0 place-items-center rounded-full border-[3px] border-fg ${tone}`}>
            <span className="font-display text-4xl font-bold tabular-nums">{score}</span>
          </div>
          <div>
            <p className="font-display text-2xl font-semibold">{Q.healthTitle}</p>
            <p className="mt-1 text-sm font-semibold text-fg-2">{Q.healthLead(audit.contents - audit.with_issues, audit.contents)}</p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {[[Q.kpiContents, audit.contents], [Q.kpiIssues, audit.with_issues], [Q.kpiFolders, audit.groups.length],
            [Q.kpiSync, status.snapshot.synced_at ? status.snapshot.synced_at.slice(0, 10) : '—']].map(([label, value]) => (
            <div key={String(label)} className="rounded-2xl border-2 border-fg bg-card p-3">
              <p className="text-xs font-bold uppercase tracking-wider text-fg-3">{label}</p>
              <p className="mt-1 font-display text-2xl font-semibold tabular-nums">{value}</p>
            </div>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" onClick={() => onGo('carte')} icon={<MapIcon size={16} />}>{Q.goMap}</Button>
          <Button onClick={() => onGo('reponses')} icon={<Sparkles size={16} />}>{Q.goAnswers}</Button>
        </div>
      </div>
      <div className="flex flex-col gap-5">
        <div className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-5">
          <h3 className="text-lg">{Q.byCategory}</h3>
          <ul className="mt-3 flex flex-col gap-2">
            {audit.categories.map((c) => (
              <li key={c.key}>
                <button disabled={!c.count} onClick={() => onGo('carte', { group: null, category: c.key })} className="group flex w-full items-center gap-3 text-left disabled:opacity-40">
                  <span className="w-36 shrink-0 text-sm font-bold group-enabled:group-hover:underline">{c.label}</span>
                  <span className="h-4 flex-1 overflow-hidden rounded-full border-2 border-fg/40 bg-card-2">
                    <span className={`block h-full ${SEV_BAR[c.severity] ?? 'bg-card-3'}`} style={{ width: `${(c.count / max) * 100}%` }} />
                  </span>
                  <span className="w-8 text-right font-bold tabular-nums">{c.count}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-5">
          <h3 className="text-lg">{Q.worstFolders}</h3>
          <ul className="mt-3 flex flex-col gap-1.5">
            {worst.map((g) => (
              <li key={g.group}>
                <button onClick={() => onGo('carte', { group: g.group, category: null })} className="flex w-full items-center justify-between gap-3 rounded-xl px-2 py-1 text-left hover:bg-card-2">
                  <span className="font-semibold">{g.group}</span>
                  <span className="text-sm font-bold tabular-nums text-fg-2">{g.with_issues} / {g.total}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}

function StatusStrip({ status, onSync, onConnect }: { status: QvidianStatus; onSync: () => void; onConnect: () => void }) {
  const connected = status.mode === 'qvidian' && status.connected
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-2xl border-[2.5px] border-fg bg-card px-3 py-2 shadow-[3px_3px_0_0_var(--color-fg)]">
      <span className={`inline-flex items-center gap-1.5 rounded-full border-2 border-fg px-2.5 py-0.5 text-xs font-bold ${status.mode === 'demo' ? 'bg-sun-400' : connected ? 'bg-mint-400' : 'bg-[#ffd6dc]'}`}>
        <span className={`size-2 rounded-full ${connected ? 'bg-fg' : 'bg-fg/40'}`} aria-hidden="true" />
        {Q.mode[status.mode]}{status.mode === 'qvidian' ? ` · ${connected ? Q.connectedAs(status.user) : Q.notConnected}` : ''}
      </span>
      <span className="inline-flex items-center gap-1 text-xs font-bold text-fg-2"><ShieldCheck size={13} aria-hidden="true" />{status.write_enabled ? Q.writeLocked : Q.readOnly}</span>
      <span className="text-xs font-semibold text-fg-3">{status.snapshot.synced_at ? Q.lastSync(status.snapshot.synced_at.replace('T', ' ').slice(0, 16), status.snapshot.count ?? '0') : Q.noSync}</span>
      <span className="ml-auto flex gap-2">
        {!connected && status.mode !== 'off' && <Button size="sm" variant="primary" onClick={onConnect} icon={<LogIn size={14} />}>{Q.sso}</Button>}
        <Button size="sm" onClick={onSync} loading={status.sync.running} disabled={status.sync.running || status.mode === 'off'} icon={<RefreshCw size={14} />}>
          {status.sync.running ? `${Q.syncing} ${status.sync.message}` : Q.sync}
        </Button>
      </span>
    </div>
  )
}

export default function Qvidian() {
  const toast = useToast()
  const root = useRef<HTMLDivElement>(null)
  const [params, setParams] = useSearchParams()
  const [status, setStatus] = useState<QvidianStatus | null>(null)
  const [audit, setAudit] = useState<QvidianAudit | null>(null)
  const [journal, setJournal] = useState<QvidianJournalEntry[]>([])
  const [error, setError] = useState<ApiError | null>(null)
  const [depth, setDepth] = useState(2)
  const [filter, setFilter] = useState<MapFilter>({ group: null, category: null })
  const [query, setQuery] = useState('')
  const [onlyIssues, setOnlyIssues] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [shown, setShown] = useState(PAGE)
  const tab = (TABS.includes(params.get('onglet') as Tab) ? params.get('onglet') : 'apercu') as Tab
  const go = (t: Tab, f?: MapFilter) => {
    if (f) setFilter(f)
    const next = new URLSearchParams(params)
    next.set('onglet', t)
    setParams(next, { replace: true })
    window.scrollTo({ top: 0, behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
  }

  useGSAP(() => {
    if (prefersReducedMotion()) return
    gsap.from('[data-enter]', { y: 18, opacity: 0, stagger: 0.05, duration: d('base'), ease: ease.out })
  }, { scope: root, dependencies: [!!status, tab] })

  const load = async () => {
    try {
      const [s, a, j] = await Promise.all([api.qvidian.status(), api.qvidian.audit(depth), api.qvidian.journal()])
      setStatus(s); setAudit(a); setJournal(j); setError(null)
    } catch (e) { setError(e instanceof ApiError ? e : new ApiError(String(e))) }
  }
  useEffect(() => { void load() }, [depth]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const sso = params.get('sso')
    if (!sso) return
    toast(sso === 'ok' ? 'success' : 'error', sso === 'ok' ? Q.ssoOk : Q.ssoFail, sso === 'ok' ? undefined : params.get('raison') ?? undefined)
    const next = new URLSearchParams(params)
    next.delete('raison'); next.delete('sso')
    if (sso !== 'ok') next.set('onglet', 'connexion')
    setParams(next, { replace: true })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!status?.sync.running) return
    const t = window.setInterval(async () => {
      const s = await api.qvidian.status()
      setStatus(s)
      if (!s.sync.running) { window.clearInterval(t); void load() }
    }, 1500)
    return () => window.clearInterval(t)
  }, [status?.sync.running]) // eslint-disable-line react-hooks/exhaustive-deps
  // Raccourcis : 1 à 7 pour les onglets (jamais pendant la saisie)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (e.metaKey || e.ctrlKey || e.altKey || t.closest('input, textarea, select, [contenteditable="true"]')) return
      const n = Number(e.key)
      if (n >= 1 && n <= TABS.length) go(TABS[n - 1])
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const items = useMemo(() => {
    if (!audit) return []
    const words = query.trim().toLowerCase()
    return audit.items.filter((it) => (!onlyIssues || it.issues.length > 0)
      && (!filter.group || it.group === filter.group)
      && (!filter.category || it.issues.some((i) => i.category === filter.category))
      && (!words || `${it.id} ${it.title} ${it.text}`.toLowerCase().includes(words)))
  }, [audit, filter, query, onlyIssues])
  useEffect(() => setShown(PAGE), [filter, query, onlyIssues])

  const toggle = (id: number, on: boolean) => setSelected((s) => { const n = new Set(s); if (on) n.add(id); else n.delete(id); return n })
  const ids = [...selected]
  const sync = async () => {
    try { await api.qvidian.sync(); setStatus(await api.qvidian.status()) } catch (e) {
      toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
      go('connexion')
    }
  }
  const sso = async () => {
    try { window.location.href = (await api.qvidian.ssoStart()).url } catch (e) {
      toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
    }
  }
  const icons: Record<Tab, typeof Gauge> = { apercu: Gauge, carte: MapIcon, bibliotheque: Library, reponses: Sparkles, ia: Bot, modifier: PenSquare, connexion: Plug }
  const badge: Partial<Record<Tab, number>> = { carte: audit?.with_issues, ia: selected.size || undefined, modifier: selected.size || undefined }

  const list = (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[14rem] flex-1">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-fg-3" size={16} aria-hidden="true" />
          <TextInput type="search" aria-label={Q.search} placeholder={Q.search} value={query} onChange={(e) => setQuery(e.target.value)} className="pl-10" />
        </div>
        <Switch checked={onlyIssues} onChange={setOnlyIssues} label={Q.onlyIssues} />
      </div>
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className="font-bold text-fg-2">{Q.filtered(items.length)}{filter.group ? ` · ${filter.group}` : ''}{filter.category && audit ? ` · ${audit.categories.find((c) => c.key === filter.category)?.label}` : ''}</span>
        {(filter.group || filter.category) && <button onClick={() => setFilter({ group: null, category: null })} className="text-xs font-bold underline">{Q.all}</button>}
        <button onClick={() => setSelected(new Set([...selected, ...items.map((i) => i.id)]))} className="ml-auto text-xs font-bold underline">{Q.selectAll}</button>
      </div>
      <ContentList items={items.slice(0, shown)} selected={selected} onToggle={toggle} />
      {items.length > shown && <Button size="sm" onClick={() => setShown((n) => n + PAGE)}>+ {Math.min(PAGE, items.length - shown)}</Button>}
    </div>
  )

  return (
    <div ref={root} className="mx-auto w-[min(100%-2rem,110rem)] pb-28 pt-8 sm:pt-10">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow"><Library size={13} aria-hidden="true" />{Q.eyebrow}</p>
          <h1 className="mt-3 text-[clamp(2rem,4.5vw,3.4rem)] font-bold leading-none">{Q.title}</h1>
        </div>
        {status && <div className="min-w-[min(100%,40rem)] flex-1"><StatusStrip status={status} onSync={sync} onConnect={sso} /></div>}
      </header>

      <nav role="tablist" aria-label={Q.tabsLabel} className="sticky top-20 z-20 mt-6 flex gap-1.5 overflow-x-auto rounded-2xl border-[2.5px] border-fg bg-canvas/95 p-1.5 backdrop-blur">
        {TABS.map((t, i) => {
          const Icon = icons[t]
          return (
            <button key={t} role="tab" aria-selected={tab === t} onClick={() => go(t)} title={`${Q.tabs[t]} (${i + 1})`}
              className={`inline-flex shrink-0 items-center gap-2 rounded-xl px-3.5 py-2 text-sm font-bold transition-colors ${tab === t ? 'bg-fg text-canvas' : 'hover:bg-card-2'}`}>
              <Icon size={16} aria-hidden="true" />{Q.tabs[t]}
              {badge[t] ? <span className={`rounded-full px-1.5 text-[0.7rem] tabular-nums ${tab === t ? 'bg-canvas text-fg' : 'bg-sun-400'}`}>{badge[t]}</span> : null}
              <kbd className="hidden text-[0.65rem] opacity-50 xl:inline">{i + 1}</kbd>
            </button>
          )
        })}
      </nav>

      {error && <div className="mt-8"><ErrorState error={error} onRetry={load} /></div>}
      {!status && !error && <Loading />}

      {status && audit && (
        <main key={tab} data-enter className="mt-6" role="tabpanel" aria-label={Q.tabs[tab]}>
          {tab === 'apercu' && <Overview audit={audit} status={status} onGo={go} />}
          {tab === 'carte' && (
            <div className="grid gap-6 2xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
              <section className="glass rounded-[var(--radius-card)] p-5">
                <div className="flex flex-wrap items-end justify-between gap-3">
                  <div>
                    <h2 className="text-2xl">{Q.mapTitle}</h2>
                    <p className="mt-1 text-sm font-semibold text-fg-2">{Q.mapLead}</p>
                  </div>
                  <Field label={Q.depth}>
                    {({ id }) => (
                      <Select id={id} value={depth} onChange={(e) => setDepth(Number(e.target.value))}>
                        {[1, 2, 3].map((n) => <option key={n} value={n}>{n}</option>)}
                      </Select>
                    )}
                  </Field>
                </div>
                <div className="mt-4"><ErrorMap audit={audit} filter={filter} onFilter={(f) => { setFilter(f); setOnlyIssues(true) }} /></div>
              </section>
              <section className="glass rounded-[var(--radius-card)] p-5">{list}</section>
            </div>
          )}
          {tab === 'bibliotheque' && <section className="glass rounded-[var(--radius-card)] p-5">{list}</section>}
          {tab === 'reponses' && <section className="glass mx-auto max-w-4xl rounded-[var(--radius-card)] p-6"><h2 className="mb-3 text-2xl">{Q.suggestTitle}</h2><SuggestPanel halfLife={status.half_life_days} /></section>}
          {tab === 'ia' && (
            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
              <section className="glass rounded-[var(--radius-card)] p-6"><h2 className="mb-3 text-2xl">{Q.aiTitle}</h2><AiPanel ids={ids} onDone={load} /></section>
              <section className="glass rounded-[var(--radius-card)] p-5"><p className="mb-3 text-sm font-bold text-fg-2">{Q.pickHint}</p>{list}</section>
            </div>
          )}
          {tab === 'modifier' && (
            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
              <section className="glass rounded-[var(--radius-card)] p-6"><h2 className="mb-3 text-2xl">{Q.bulkTitle}</h2><BulkPanel ids={ids} writeEnabled={status.write_enabled} journal={journal} onWritten={load} /></section>
              <section className="glass rounded-[var(--radius-card)] p-5"><p className="mb-3 text-sm font-bold text-fg-2">{Q.pickHint}</p>{list}</section>
            </div>
          )}
          {tab === 'connexion' && (
            <div className="grid gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
              <section className="glass rounded-[var(--radius-card)] p-6"><h2 className="mb-3 text-2xl">{Q.connectTitle}</h2><ConnectionPanel status={status} onChange={(s) => { setStatus(s); void load() }} /></section>
              <section className="glass rounded-[var(--radius-card)] p-6"><h2 className="mb-3 text-2xl">{Q.projectsTitle}</h2><ProjectsPanel /></section>
            </div>
          )}
        </main>
      )}

      {selected.size > 0 && (
        <div className="fixed inset-x-0 bottom-4 z-30 mx-auto flex w-[min(100%-2rem,44rem)] flex-wrap items-center gap-2 rounded-2xl border-[2.5px] border-fg bg-card px-4 py-2.5 shadow-[var(--shadow-pop)]" role="region" aria-label={Q.selected(selected.size)}>
          <Activity size={16} aria-hidden="true" />
          <span className="font-display font-semibold">{Q.selected(selected.size)}</span>
          <span className="ml-auto flex flex-wrap gap-2">
            <Button size="sm" onClick={() => go('ia')} icon={<Bot size={14} />}>{Q.trayAi}</Button>
            <Button size="sm" variant="primary" onClick={() => go('modifier')} icon={<PenSquare size={14} />}>{Q.trayEdit}</Button>
            <button onClick={() => setSelected(new Set())} aria-label={Q.unselect} className="rounded-full border-2 border-fg/30 p-1.5 hover:border-fg"><X size={14} /></button>
          </span>
        </div>
      )}
    </div>
  )
}
