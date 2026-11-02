/** Vues Santé (carte des erreurs), Réponses types, Analyse IA, Journal et Connexion de la section Qvidian. */
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { LogIn, LogOut, RotateCcw, Search, ShieldCheck, Upload } from 'lucide-react'
import { AiPanel } from '../../../components/qvidian/AiPanel'
import { ContentList } from '../../../components/qvidian/ContentList'
import { ErrorMap, type MapFilter } from '../../../components/qvidian/ErrorMap'
import { Button } from '../../../components/ui/Button'
import { Field, Select, Switch, TextInput } from '../../../components/ui/Field'
import { useToast } from '../../../components/ui/Toast'
import { texts } from '../../../content/texts'
import { api, ApiError } from '../../../lib/api'
import type { QvidianItem, QvidianStatus, QvidianSuggest } from '../../../lib/types'
import { useQvidian } from '../context'

const Q = texts.qvidian
const PAGE = 60

function Title({ title, lead }: { title: string; lead?: string }) {
  return (
    <header data-enter>
      <h1 className="text-[clamp(1.8rem,3.6vw,2.8rem)] font-bold leading-none">{title}</h1>
      {lead && <p className="mt-2 max-w-3xl text-sm font-semibold text-fg-2">{lead}</p>}
    </header>
  )
}

function ItemList({ items }: { items: QvidianItem[] }) {
  const { selected, toggle, select } = useQvidian()
  const [query, setQuery] = useState('')
  const [shown, setShown] = useState(PAGE)
  const rows = useMemo(() => {
    const w = query.trim().toLowerCase()
    return items.filter((it) => !w || `${it.id} ${it.title} ${it.text}`.toLowerCase().includes(w))
  }, [items, query])
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[14rem] flex-1">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-fg-3" size={16} aria-hidden="true" />
          <TextInput type="search" aria-label={Q.search} placeholder={Q.search} value={query} onChange={(e) => setQuery(e.target.value)} className="pl-10" />
        </div>
        <button onClick={() => select(rows.map((i) => i.id))} className="text-xs font-bold underline">{Q.selectAll} ({rows.length})</button>
      </div>
      <ContentList items={rows.slice(0, shown)} selected={selected} onToggle={toggle} />
      {rows.length > shown && <Button size="sm" onClick={() => setShown((n) => n + PAGE)}>+ {Math.min(PAGE, rows.length - shown)}</Button>}
    </div>
  )
}

export function HealthView() {
  const { audit, depth, setDepth } = useQvidian()
  const [filter, setFilter] = useState<MapFilter>({ group: null, category: null })
  const [onlyIssues, setOnlyIssues] = useState(true)
  if (!audit) return null
  const items = audit.items.filter((it) => (!onlyIssues || it.issues.length > 0) && (!filter.group || it.group === filter.group)
    && (!filter.category || it.issues.some((i) => i.category === filter.category)))
  return (
    <div className="flex flex-col gap-5">
      <Title title={Q.mapTitle} lead={Q.mapLead} />
      <div className="grid gap-5 2xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <section data-enter className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="flex flex-wrap gap-2 text-xs font-bold">
              {audit.categories.filter((c) => c.count).map((c) => (
                <button key={c.key} onClick={() => setFilter({ group: null, category: filter.category === c.key ? null : c.key })} aria-pressed={filter.category === c.key}
                  className={`rounded-full border-2 px-2.5 py-0.5 ${filter.category === c.key ? 'border-fg bg-sun-400' : 'border-fg/30 hover:border-fg'}`}>
                  {c.label} {c.count}
                </button>
              ))}
            </div>
            <Field label={Q.depth}>
              {({ id }) => (
                <Select id={id} value={depth} onChange={(e) => setDepth(Number(e.target.value))}>{[1, 2, 3].map((n) => <option key={n} value={n}>{n}</option>)}</Select>
              )}
            </Field>
          </div>
          <div className="mt-4"><ErrorMap audit={audit} filter={filter} onFilter={(f) => { setFilter(f); setOnlyIssues(true) }} /></div>
        </section>
        <section data-enter className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-5">
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <p className="text-sm font-bold text-fg-2">{Q.filtered(items.length)}{filter.group ? ` · ${filter.group}` : ''}</p>
            {(filter.group || filter.category) && <button onClick={() => setFilter({ group: null, category: null })} className="text-xs font-bold underline">{Q.all}</button>}
            <span className="ml-auto"><Switch checked={onlyIssues} onChange={setOnlyIssues} label={Q.onlyIssues} /></span>
          </div>
          <ItemList items={items} />
        </section>
      </div>
    </div>
  )
}

export function AnswersView() {
  const { status } = useQvidian()
  const [q, setQ] = useState('')
  const [res, setRes] = useState<QvidianSuggest | null>(null)
  const [busy, setBusy] = useState(false)
  const go = async () => {
    if (!q.trim()) return
    setBusy(true)
    try { setRes(await api.qvidian.suggest(q)) } finally { setBusy(false) }
  }
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-5">
      <Title title={Q.suggestTitle} lead={Q.suggestLead} />
      <form data-enter className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void go() }}>
        <TextInput aria-label={Q.suggestPlaceholder} value={q} onChange={(e) => setQ(e.target.value)} placeholder={Q.suggestPlaceholder} />
        <Button type="submit" loading={busy} icon={<Search size={16} />}>{Q.suggestGo}</Button>
      </form>
      {status && <p className="text-xs font-semibold text-fg-3">{Q.halfLife(status.half_life_days)}</p>}
      {res && res.choices.length === 0 && <p className="text-sm font-semibold">{Q.suggestNone}</p>}
      {res?.choices.map((c, i) => (
        <article key={i} data-enter className={`rounded-2xl border-2 p-4 ${i === 0 ? 'border-fg bg-sun-400/20 shadow-[4px_4px_0_0_var(--color-fg)]' : 'border-fg/25 bg-card'}`}>
          <div className="flex items-center gap-2">
            <span className="h-2.5 flex-1 overflow-hidden rounded-full border border-fg/40 bg-card-2"><span className="block h-full bg-magic-400" style={{ width: `${Math.max(4, Math.round(c.share * 100))}%` }} /></span>
            <span className="text-xs font-bold tabular-nums">{Math.round(c.share * 100)} %</span>
          </div>
          <p className="mt-2 whitespace-pre-line text-sm font-semibold">{c.value}</p>
          <p className="mt-1 text-xs font-semibold text-fg-2">{c.why} · {c.contents.map((x) => <Link key={x} to={`/qvidian/contenu/${x}`} className="mr-1 underline">#{x}</Link>)}</p>
        </article>
      ))}
    </div>
  )
}

export function AiView() {
  const { audit, selected, reload } = useQvidian()
  const ids = [...selected]
  const items = (audit?.items ?? []).filter((i) => selected.has(i.id))
  return (
    <div className="flex flex-col gap-5">
      <Title title={Q.aiTitle} lead={Q.aiLead} />
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <section data-enter className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-5"><AiPanel ids={ids} onDone={reload} /></section>
        <section data-enter className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-5">
          <p className="mb-3 text-sm font-bold text-fg-2">{ids.length ? Q.selected(ids.length) : Q.emptySelection}</p>
          <ItemList items={items.length ? items : audit?.items.filter((i) => i.issues.length) ?? []} />
        </section>
      </div>
    </div>
  )
}

export function JournalView() {
  const { journal, status, reload, fail } = useQvidian()
  const toast = useToast()
  const [undoing, setUndoing] = useState<string | null>(null)
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const undo = async (batch: string) => {
    setBusy(true)
    try {
      const r = await api.qvidian.undo(batch, password)
      toast(r.failed ? 'error' : 'success', Q.applied(r.written, r.skipped, r.failed))
      setUndoing(null); setPassword('')
      void reload()
    } catch (e) { fail(e) } finally { setBusy(false) }
  }
  return (
    <div className="flex flex-col gap-5">
      <Title title={Q.journalTitle} />
      {journal.length === 0 ? <p className="text-sm font-semibold text-fg-3">{Q.noJournal}</p> : (
        <ol className="flex flex-col gap-3">
          {journal.map((j) => (
            <li key={j.batch} data-enter className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-4">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-display font-semibold">{j.label}</span>
                <span className="text-xs font-semibold text-fg-3">{j.at.replace('T', ' ')} · {j.user} · {j.items.filter((i) => i.ok).length} écrit(s){j.force ? ` · ${Q.forced}` : ''}{j.source === 'demo' ? ' · démo' : ''}{j.undo_of ? ` · annule ${j.undo_of}` : ''}</span>
                {!j.undo_of && j.items.some((i) => i.ok) && status?.write_enabled && (
                  <button onClick={() => setUndoing(undoing === j.batch ? null : j.batch)} className="ml-auto inline-flex items-center gap-1 rounded-full border-2 border-fg/40 px-2.5 py-0.5 text-xs font-bold hover:border-fg">
                    <RotateCcw size={12} aria-hidden="true" />{Q.undo}
                  </button>
                )}
              </div>
              <ul className="mt-2 flex flex-col gap-0.5 text-xs">
                {j.items.slice(0, 8).map((it) => (
                  <li key={it.id} className={it.ok ? 'font-semibold' : 'text-fg-3'}>
                    <Link to={`/qvidian/contenu/${it.id}`} className="underline">#{it.id}</Link> {it.title} · {it.field} : <s>{String(it.before ?? '—').slice(0, 60)}</s> → {String(it.after ?? '—').slice(0, 60)}
                  </li>
                ))}
              </ul>
              {undoing === j.batch && (
                <form className="mt-3 flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); void undo(j.batch) }}>
                  <Field label={Q.teamPassword}>{({ id }) => <TextInput id={id} type="password" autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)} />}</Field>
                  <Button type="submit" size="sm" variant="danger" disabled={!password || busy}>{Q.undo}</Button>
                </form>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

function ConnectionPanel({ status, onChange }: { status: QvidianStatus; onChange: () => void }) {
  const { fail } = useQvidian()
  const [user, setUser] = useState('')
  const [password, setPassword] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [busy, setBusy] = useState(false)
  const connect = async () => {
    setBusy(true)
    try { await api.qvidian.connect(user, password, apiKey); setPassword(''); setApiKey(''); onChange() } catch (e) { fail(e) } finally { setBusy(false) }
  }
  const sso = async () => {
    try { window.location.href = (await api.qvidian.ssoStart()).url } catch (e) { fail(e) }
  }
  const connected = status.mode === 'qvidian' && status.connected
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className={`rounded-full border-[2.5px] border-fg px-3 py-1 text-sm font-bold ${status.mode === 'demo' ? 'bg-sun-400' : connected ? 'bg-mint-400' : 'bg-card-3'}`}>
          {Q.mode[status.mode]}{status.mode === 'qvidian' ? ` · ${connected ? Q.connectedAs(status.user) : Q.notConnected}` : ''}
        </span>
        <span className="inline-flex items-center gap-1.5 rounded-full border-2 border-fg/40 px-3 py-1 text-xs font-bold">
          <ShieldCheck size={14} aria-hidden="true" />{Q.readOnly} · {status.write_enabled ? Q.writeLocked : Q.writeOff}
        </span>
        {connected && !status.credentials && (
          <Button size="sm" variant="ghost" className="ml-auto" onClick={async () => { await api.qvidian.disconnect(); onChange() }} icon={<LogOut size={15} />}>{Q.disconnect}</Button>
        )}
      </div>
      {status.mode !== 'off' && !connected && (
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border-[2.5px] border-fg bg-sun-400/30 p-3">
          <Button variant="primary" onClick={sso} disabled={!status.sso} icon={<LogIn size={17} />}>{Q.sso}</Button>
          <p className="min-w-[16rem] flex-1 text-sm font-semibold text-fg-2">{status.sso_suffix ? Q.ssoHint : Q.ssoNoSuffix}</p>
          {status.last_sso_error && <p role="alert" className="w-full text-sm font-bold text-danger">{Q.ssoLast} {status.last_sso_error}</p>}
        </div>
      )}
      {status.mode !== 'off' && !connected && (
        <details className="rounded-2xl border-2 border-fg/20 bg-card p-3" open={status.mode === 'demo'}>
          <summary className="cursor-pointer font-display font-semibold">{Q.connectOther}</summary>
          <p className="mt-1 text-xs font-semibold text-fg-3">{Q.connectHint}</p>
          <form className="mt-3 grid gap-3 sm:grid-cols-4" onSubmit={(e) => { e.preventDefault(); void connect() }}>
            <Field label={Q.user}>{({ id }) => <TextInput id={id} autoComplete="username" value={user} onChange={(e) => setUser(e.target.value)} />}</Field>
            <Field label={Q.password}>{({ id }) => <TextInput id={id} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />}</Field>
            <Field label={Q.apiKey}>{({ id }) => <TextInput id={id} type="password" autoComplete="off" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />}</Field>
            <div className="flex items-end"><Button type="submit" variant="primary" disabled={!user || (!password && !apiKey) || busy} loading={busy} icon={<LogIn size={16} />}>{Q.connect}</Button></div>
          </form>
        </details>
      )}
    </section>
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
        {({ id }) => <Select id={id} value={limit} onChange={(e) => setLimit(Number(e.target.value))}>{[10, 20, 50, 100].map((n) => <option key={n} value={n}>{n}</option>)}</Select>}
      </Field>
      <Button onClick={go} loading={busy} disabled={busy} icon={<Upload size={16} />}>{Q.projectsGo(limit)}</Button>
    </div>
  )
}

export function ConnectionView() {
  const { status, reload } = useQvidian()
  if (!status) return null
  return (
    <div className="flex flex-col gap-5">
      <Title title={Q.connectTitle} />
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <section data-enter className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-6"><ConnectionPanel status={status} onChange={() => void reload()} /></section>
        <section data-enter className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-6"><h2 className="mb-3 text-2xl">{Q.projectsTitle}</h2><ProjectsPanel /></section>
      </div>
    </div>
  )
}
