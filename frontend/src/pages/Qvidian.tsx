/**
 * Fenêtre Qvidian : connexion (identifiant, clé d'API ou SSO), instantané local de la bibliothèque, carte des erreurs,
 * analyse IA par Copilot, réponse type agrégée (utilisations × récence), modifications en masse protégées par mot de passe,
 * import des projets comme anciens RFI. Lecture seule par défaut.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Bot, Library, LogIn, LogOut, PenSquare, RefreshCw, Search, ShieldCheck, Sparkles, Upload } from 'lucide-react'
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
type Tab = 'ai' | 'bulk' | 'suggest' | 'projects'
const PAGE = 60

function StatusBar({ status, onChange }: { status: QvidianStatus; onChange: (s: QvidianStatus) => void }) {
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
    <section data-enter className="glass mt-8 flex flex-col gap-4 rounded-[var(--radius-card)] p-5 sm:p-6">
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
        <details className="rounded-2xl border-2 border-fg/20 bg-card p-3">
          <summary className="cursor-pointer font-display font-semibold">{Q.connectTitle}</summary>
          <p className="mt-1 text-xs font-semibold text-fg-3">{Q.connectHint}</p>
          <form className="mt-3 grid gap-3 sm:grid-cols-4" onSubmit={(e) => { e.preventDefault(); void connect() }}>
            <Field label={Q.user}>{({ id }) => <TextInput id={id} autoComplete="username" value={user} onChange={(e) => setUser(e.target.value)} />}</Field>
            <Field label={Q.password}>{({ id }) => <TextInput id={id} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />}</Field>
            <Field label={Q.apiKey}>{({ id }) => <TextInput id={id} type="password" autoComplete="off" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />}</Field>
            <div className="flex items-end gap-2">
              <Button type="submit" variant="primary" disabled={!user || (!password && !apiKey) || busy} loading={busy} icon={<LogIn size={16} />}>{Q.connect}</Button>
            </div>
          </form>
          {status.sso && <Button className="mt-3" size="sm" onClick={sso} icon={<LogIn size={15} />}>{Q.sso}</Button>}
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
  const [onlyIssues, setOnlyIssues] = useState(true)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [tab, setTab] = useState<Tab>('ai')
  const [shown, setShown] = useState(PAGE)

  useGSAP(() => {
    if (prefersReducedMotion()) return
    gsap.from('[data-enter]', { y: 24, opacity: 0, stagger: 0.07, duration: d('slow'), ease: ease.out })
  }, { scope: root, dependencies: [!!status] })

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
    toast(sso === 'ok' ? 'success' : 'error', sso === 'ok' ? Q.ssoOk : Q.ssoFail)
    params.delete('sso'); setParams(params, { replace: true })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  // Pendant une synchronisation : on suit l'avancement, puis on recharge la carte
  useEffect(() => {
    if (!status?.sync.running) return
    const t = window.setInterval(async () => {
      const s = await api.qvidian.status()
      setStatus(s)
      if (!s.sync.running) { window.clearInterval(t); void load() }
    }, 1500)
    return () => window.clearInterval(t)
  }, [status?.sync.running]) // eslint-disable-line react-hooks/exhaustive-deps

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

  return (
    <div ref={root} className="mx-auto w-[min(100%-2rem,96rem)] pt-10 sm:pt-14">
      <header data-enter className="max-w-3xl">
        <p className="eyebrow"><Library size={13} aria-hidden="true" />{Q.eyebrow}</p>
        <h1 className="mt-4 text-[clamp(2.4rem,6vw,4.5rem)] font-bold">{Q.title}</h1>
        <p className="mt-4 text-lg font-semibold text-fg-2">{Q.lead}</p>
      </header>

      {error && <div className="mt-8"><ErrorState error={error} onRetry={load} /></div>}
      {!status && !error && <Loading />}
      {status && <StatusBar status={status} onChange={(s) => { setStatus(s); void load() }} />}

      {audit && status && (
        <div className="mt-8 grid gap-6 xl:grid-cols-[minmax(0,1.6fr)_minmax(24rem,1fr)]">
          <div className="flex min-w-0 flex-col gap-6">
            <section data-enter className="glass rounded-[var(--radius-card)] p-5 sm:p-6">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <h2 className="text-2xl">{Q.mapTitle}</h2>
                  <p className="mt-1 text-sm font-semibold text-fg-2">{Q.mapLead} {audit.with_issues} / {audit.contents} {Q.total}.</p>
                </div>
                <Field label={Q.depth}>
                  {({ id }) => (
                    <Select id={id} value={depth} onChange={(e) => setDepth(Number(e.target.value))}>
                      {[1, 2, 3].map((n) => <option key={n} value={n}>{n}</option>)}
                    </Select>
                  )}
                </Field>
              </div>
              <div className="mt-4"><ErrorMap audit={audit} filter={filter} onFilter={setFilter} /></div>
            </section>

            <section data-enter className="glass rounded-[var(--radius-card)] p-5 sm:p-6">
              <div className="flex flex-wrap items-center gap-3">
                <h2 className="text-2xl">{Q.listTitle}</h2>
                <span className="text-sm font-bold text-fg-2">{Q.filtered(items.length)}{filter.group ? ` · ${filter.group}` : ''}{filter.category ? ` · ${audit.categories.find((c) => c.key === filter.category)?.label}` : ''}</span>
                {(filter.group || filter.category) && <button onClick={() => setFilter({ group: null, category: null })} className="text-xs font-bold underline">{Q.all}</button>}
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <div className="relative min-w-[14rem] flex-1">
                  <Search className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-fg-3" size={16} aria-hidden="true" />
                  <TextInput type="search" aria-label={Q.search} placeholder={Q.search} value={query} onChange={(e) => setQuery(e.target.value)} className="pl-10" />
                </div>
                <Switch checked={onlyIssues} onChange={setOnlyIssues} label={Q.onlyIssues} />
                <button onClick={() => setSelected(new Set(items.map((i) => i.id)))} className="text-xs font-bold underline">{Q.selectAll}</button>
                {selected.size > 0 && <button onClick={() => setSelected(new Set())} className="text-xs font-bold underline">{Q.unselect}</button>}
              </div>
              <div className="mt-4">
                <ContentList items={items.slice(0, shown)} selected={selected} onToggle={toggle} />
                {items.length > shown && <Button className="mt-3" size="sm" onClick={() => setShown((n) => n + PAGE)}>+ {Math.min(PAGE, items.length - shown)}</Button>}
              </div>
            </section>
          </div>

          <aside data-enter className="glass flex flex-col gap-4 self-start rounded-[var(--radius-card)] p-5 sm:p-6 xl:sticky xl:top-24">
            <p className="font-display text-lg font-semibold">{Q.selected(selected.size)}</p>
            <div className="flex flex-wrap gap-1.5" role="tablist">
              {([['ai', Q.aiTitle, Bot], ['bulk', Q.bulkTitle, PenSquare], ['suggest', Q.suggestTitle, Sparkles], ['projects', Q.projectsTitle, Upload]] as const).map(([k, label, Icon]) => (
                <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
                  className={`inline-flex items-center gap-1.5 rounded-full border-2 px-3 py-1 text-xs font-bold ${tab === k ? 'border-fg bg-magic-500 text-white' : 'border-fg/30 hover:border-fg'}`}>
                  <Icon size={13} aria-hidden="true" />{label}
                </button>
              ))}
            </div>
            {tab === 'ai' && <AiPanel ids={ids} onDone={load} />}
            {tab === 'bulk' && <BulkPanel ids={ids} writeEnabled={status.write_enabled} journal={journal} onWritten={load} />}
            {tab === 'suggest' && <SuggestPanel halfLife={status.half_life_days} />}
            {tab === 'projects' && <ProjectsPanel />}
          </aside>
        </div>
      )}
    </div>
  )
}
