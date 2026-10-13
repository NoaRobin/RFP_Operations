/**
 * Documents des fonds : la liste des PDF du site (DIC, prospectus, reportings, SFDR), faite ici ou dans Excel (liste
 * vierge), téléchargée en un clic ou chaque mois. Chaque ligne affiche son état ; un échec dit pourquoi et quoi faire.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, CalendarClock, Check, CheckCircle2, Download, ExternalLink, FileDown, FileSpreadsheet, FileText, Link2,
  Loader2, Search, Stethoscope, Trash2, Upload, Wand2, XCircle } from 'lucide-react'
import { AvailablePanel, type Pick } from '../components/fundshop/AvailablePanel'
import { ScheduleDialog } from '../components/ScheduleDialog'
import { Button } from '../components/ui/Button'
import { ErrorState, Loading } from '../components/ui/States'
import { useToast } from '../components/ui/Toast'
import { texts } from '../content/texts'
import { api, ApiError } from '../lib/api'
import type { FundEntry, FundShopDiagnostic, FundShopItem, FundShopOverview, FundShopProblem } from '../lib/types'

const T = texts.fundshop
const AUTOMATION = 'telechargement_documents'
const RELATIVE = ['M-1', 'M-2', 'M-3']
const NETWORK = ['proxy', 'certificat', 'hors-ligne', 'delai', 'reseau', 'refuse', 'dossier']

function lastMonth(): string {
  const d = new Date()
  d.setDate(1)
  d.setMonth(d.getMonth() - 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

function FundSearch({ onPick }: { onPick: (fund: string, part: string, isin: string) => void }) {
  const [q, setQ] = useState('')
  const [funds, setFunds] = useState<FundEntry[]>([])
  useEffect(() => {
    if (q.trim().length < 2) { setFunds([]); return }
    const id = window.setTimeout(() => api.rfi.funds(q).then(setFunds).catch(() => setFunds([])), 200)
    return () => window.clearTimeout(id)
  }, [q])
  return (
    <div className="relative w-full max-w-md">
      <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-3" size={16} aria-hidden="true" />
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={T.search} aria-label={T.search}
        className="w-full rounded-full border-2 border-fg bg-card py-2 pl-9 pr-3 text-sm font-semibold focus:outline-none focus:shadow-[3px_3px_0_0_var(--color-magic-500)]" />
      {funds.length > 0 && (
        <ul className="absolute z-30 mt-1 max-h-72 w-full overflow-auto rounded-2xl border-2 border-fg bg-card p-1 shadow-[var(--shadow-pop)]">
          {funds.flatMap((f) => f.shares.map((s) => (
            <li key={s.isin}>
              <button onClick={() => { onPick(f.name, s.name, s.isin); setQ(''); setFunds([]) }}
                className="flex w-full flex-col rounded-xl px-3 py-1.5 text-left text-sm hover:bg-sun-400">
                <span className="font-semibold">{s.name}</span><span className="text-xs text-fg-3">{s.isin} · {f.name}</span>
              </button>
            </li>
          )))}
        </ul>
      )}
    </div>
  )
}

/** Ce qui ne va pas, en clair : pourquoi, puis quoi faire. */
function ProblemBox({ p, onLink }: { p: FundShopProblem; onLink?: () => void }) {
  return (
    <div className="text-xs font-semibold">
      <p className="flex items-center gap-1 font-bold text-danger"><XCircle size={14} aria-hidden="true" />{p.title}</p>
      <p className="mt-0.5 text-fg-2">{p.why}</p>
      <p className="mt-0.5"><span className="font-bold">{T.whatToDo}</span> {p.fix}</p>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {onLink && ['adresse-inconnue', 'autre-part', 'absent', 'pas-pdf'].includes(p.code) && (
          <button onClick={onLink} className="inline-flex items-center gap-1 rounded-full border-2 border-fg bg-sun-400 px-2.5 py-0.5 font-bold">
            <Link2 size={12} aria-hidden="true" />{T.haveLink}
          </button>
        )}
        {p.link && (
          <a href={p.link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-full border-2 border-fg/40 px-2.5 py-0.5 font-bold hover:border-fg">
            <ExternalLink size={12} aria-hidden="true" />{T.openPage}
          </a>
        )}
      </div>
    </div>
  )
}

function LinkForm({ item, onDone }: { item: FundShopItem; onDone: () => void }) {
  const toast = useToast()
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async () => {
    setBusy(true)
    try {
      const r = await api.fundshop.link(item.isin, url, item.kind)
      toast('success', r.message)
      onDone()
    } catch (e) {
      toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
    } finally { setBusy(false) }
  }
  return (
    <div className="mt-2 rounded-2xl border-2 border-dashed border-fg/40 bg-card-2 p-3">
      <label className="text-xs font-bold uppercase tracking-wider text-fg-3" htmlFor={`link-${item.id}`}>{T.linkLabel}</label>
      <div className="mt-1 flex flex-wrap gap-2">
        <input id={`link-${item.id}`} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…pdf" autoFocus
          className="min-w-[16rem] flex-1 rounded-xl border-2 border-fg bg-card px-2 py-1 text-sm font-semibold" />
        <Button size="sm" onClick={submit} loading={busy} disabled={!url.trim()} icon={<Check size={14} />}>{T.linkSave}</Button>
      </div>
      <p className="mt-1 text-xs font-semibold text-fg-3">{T.linkHint}</p>
    </div>
  )
}

function Status({ it, preview, onLink, blocked }: { it: FundShopItem; preview?: FundShopProblem | 'ok' | 'testing'; onLink: () => void; blocked: boolean }) {
  if (preview === 'testing') return <p className="flex items-center gap-1 text-xs font-semibold text-fg-3"><Loader2 size={13} className="motion-safe:animate-spin" />{T.testing}</p>
  if (preview === 'ok') return <p className="flex items-center gap-1 text-xs font-bold text-mint-300"><CheckCircle2 size={14} />{T.testOk}</p>
  if (preview) return <ProblemBox p={preview} onLink={onLink} />
  const r = it.result
  if (r?.status === 'OK') {
    return (
      <div className="text-xs font-semibold">
        <p className="flex items-center gap-1 font-bold text-mint-300"><CheckCircle2 size={14} aria-hidden="true" />{T.ok}
          <a href={api.fundshop.fileUrl(r.file)} target="_blank" rel="noreferrer" className="ml-1 underline">{T.open}</a></p>
        <p className="text-fg-3">{r.why}</p>
      </div>
    )
  }
  if (r?.status === 'ÉCHEC' && blocked && NETWORK.includes(r.code)) {
    return <p className="flex items-center gap-1 text-xs font-bold text-danger"><XCircle size={14} aria-hidden="true" />{r.title} <span className="font-semibold text-fg-3">{T.seeBelow}</span></p>
  }
  if (r?.status === 'ÉCHEC') return <ProblemBox p={r} onLink={onLink} />
  if (r?.status === 'DÉJÀ PRÉSENT' || it.present) return <p className="text-xs font-semibold text-fg-2">✓ {T.present}</p>
  return <p className="text-xs font-semibold text-fg-3">{T.notRun}</p>
}

export default function FundShop() {
  const toast = useToast()
  const [data, setData] = useState<FundShopOverview | null>(null)
  const [items, setItems] = useState<FundShopItem[]>([])
  const [error, setError] = useState<ApiError | null>(null)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved'>('idle')
  const [runId, setRunId] = useState<string | null>(null)
  const [scheduling, setScheduling] = useState(false)
  const [importErrors, setImportErrors] = useState<string[]>([])
  const [linkFor, setLinkFor] = useState<string | null>(null)
  const [previews, setPreviews] = useState<Record<string, FundShopProblem | 'ok' | 'testing'>>({})
  const [diag, setDiag] = useState<FundShopDiagnostic | 'loading' | null>(null)
  const [browsing, setBrowsing] = useState<{ isin: string; fund: string; part: string } | null>(null)
  const saveTimer = useRef(0)
  const version = useRef(0)

  const load = (o: FundShopOverview) => { setData(o); setItems(o.items) }
  useEffect(() => { api.fundshop.overview().then(load).catch((e) => setError(e)) }, [])

  // Enregistrement automatique : pas de bouton « Enregistrer » à oublier
  const persist = (next: FundShopItem[]) => {
    setItems(next)
    setSaveState('saving')
    const v = ++version.current
    window.clearTimeout(saveTimer.current)
    saveTimer.current = window.setTimeout(async () => {
      try {
        const o = await api.fundshop.save(next.map(({ target, period_label, present, error: _e, result, ...rest }) => ({ ...rest, id: rest.id.startsWith('new-') ? undefined : rest.id })))
        if (v === version.current) { load(o); setSaveState('saved') }
      } catch (e) {
        setSaveState('idle')
        toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
      }
    }, 500)
  }
  const flush = async () => {
    window.clearTimeout(saveTimer.current)
    if (saveState !== 'saving') return
    load(await api.fundshop.save(items.map(({ target, period_label, present, error: _e, result, ...rest }) => ({ ...rest, id: rest.id.startsWith('new-') ? undefined : rest.id }))))
    setSaveState('saved')
  }

  const types = data?.types ?? []
  const needsMonth = useMemo(() => Object.fromEntries(types.map((t) => [t.key, t.needs_month])), [types])
  const update = (id: string, patch: Partial<FundShopItem>) => {
    setPreviews((p) => { const n = { ...p }; delete n[id]; return n })
    persist(items.map((x) => (x.id === id ? { ...x, ...patch, result: null } : x)))
  }
  const add = (fund: string, part: string, isin: string) => setBrowsing({ isin, fund, part })
  const addPicks = (picks: Pick[], fund: string, part: string) => {
    if (!browsing) return
    const now = Date.now()
    persist([...items, ...picks.map((p, i) => ({ id: `new-${now}-${i}`, isin: browsing.isin, fund, part, kind: p.kind, month: p.month,
      filename: '', active: true, overwrite: false }))])
    toast('success', T.added(picks.length))
    setBrowsing(null)
  }

  // Lancement : l'automatisation tourne en arrière-plan, la page se met à jour à la fin
  useEffect(() => {
    if (!runId) return
    const id = window.setInterval(async () => {
      const run = await api.getRun(runId).catch(() => null)
      if (!run || run.status === 'queued' || run.status === 'running') return
      window.clearInterval(id)
      setRunId(null)
      const o = await api.fundshop.overview()
      load(o)
      const rs = o.items.map((i) => i.result).filter(Boolean)
      if (o.last_run?.blocked) toast('error', T.blocked, o.last_run.blocked.title)
      else toast('success', T.summary(rs.filter((r) => r?.status === 'OK').length, rs.filter((r) => r?.status === 'DÉJÀ PRÉSENT').length,
        rs.filter((r) => r?.status === 'ÉCHEC').length))
    }, 1500)
    return () => window.clearInterval(id)
  }, [runId])

  const runNow = async () => {
    await flush()
    setPreviews({})
    try {
      const run = await api.run(AUTOMATION, { mode: 'missing' })
      setRunId(run.id)
    } catch (e) {
      toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
    }
  }
  const importFile = async (file: File) => {
    await flush()
    try {
      const o = await api.fundshop.importExcel(file)
      load(o)
      setImportErrors(o.errors ?? [])
      toast('success', T.imported(o.imported ?? 0, o.duplicates ?? 0))
    } catch (e) {
      toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
    }
  }
  const learn = async (file: File) => {
    try {
      const r = await api.fundshop.learnCsv(file)
      toast('success', T.learned(r.learned))
      load(await api.fundshop.overview())
    } catch (e) {
      toast('error', e instanceof ApiError ? e.message : texts.errors.generic)
    }
  }
  const test = async (it: FundShopItem) => {
    setPreviews((p) => ({ ...p, [it.id]: 'testing' }))
    try {
      const r = await api.fundshop.tryOne(it.isin, it.kind, it.month, it.fund)
      setPreviews((p) => ({ ...p, [it.id]: r.found ? 'ok' : r.problem! }))
    } catch (e) {
      setPreviews((p) => { const n = { ...p }; delete n[it.id]; return n })
      toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
    }
  }
  const diagnose = async () => {
    setDiag('loading')
    try { setDiag(await api.fundshop.diagnostic()) } catch { setDiag(null) }
  }

  if (error) return <div className="mx-auto w-[min(100%-2rem,82rem)] pt-14"><ErrorState error={error} /></div>
  if (!data) return <Loading />
  const results = items.map((i) => i.result).filter(Boolean)
  const counts = { ok: results.filter((r) => r?.status === 'OK').length, present: results.filter((r) => r?.status === 'DÉJÀ PRÉSENT').length,
    failed: results.filter((r) => r?.status === 'ÉCHEC').length }
  const active = items.filter((i) => i.active).length

  return (
    <div className="mx-auto w-[min(100%-2rem,82rem)] pt-10 sm:pt-14">
      <header className="max-w-3xl">
        <p className="eyebrow"><FileText size={13} aria-hidden="true" />{T.eyebrow}</p>
        <h1 className="mt-4 text-[clamp(2.2rem,5.5vw,4rem)] font-bold">{T.title}</h1>
        <p className="mt-4 text-lg font-semibold text-fg-2">{T.lead}</p>
      </header>

      <section className="glass mt-8 rounded-[var(--radius-card)] p-5 sm:p-7" aria-labelledby="fs-list">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="fs-list" className="text-2xl">{T.step1}</h2>
          <span className="text-xs font-semibold text-fg-3" aria-live="polite">{saveState === 'saving' ? T.saving : saveState === 'saved' ? `✓ ${T.saved}` : ''}</span>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <FundSearch onPick={add} />
          <a href={api.fundshop.templateUrl()} title={T.blankHint}
            className="inline-flex items-center gap-2 rounded-full border-2 border-fg bg-card px-4 py-2 text-sm font-bold hover:bg-sun-400">
            <FileSpreadsheet size={15} aria-hidden="true" />{T.blank}
          </a>
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-full border-2 border-fg bg-card px-4 py-2 text-sm font-bold hover:bg-sun-400">
            <Upload size={15} aria-hidden="true" />{T.importExcel}
            <input type="file" accept=".xlsx,.xlsm" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) void importFile(f); e.target.value = '' }} />
          </label>
          {items.length > 0 && (
            <a href={api.fundshop.templateUrl(true)} className="inline-flex items-center gap-2 rounded-full border-2 border-fg/40 px-4 py-2 text-sm font-bold hover:border-fg">
              <FileDown size={15} aria-hidden="true" />{T.exportList}
            </a>
          )}
        </div>
        <p className="mt-2 text-xs font-semibold text-fg-3">{T.blankHint}</p>
        {browsing && <AvailablePanel {...browsing} existing={items.filter((i) => i.isin === browsing.isin).map((i) => ({ kind: i.kind, month: i.month }))}
          onAdd={addPicks} onClose={() => setBrowsing(null)} />}
        {importErrors.length > 0 && (
          <div className="mt-3 rounded-2xl border-2 border-warning bg-sun-400/20 p-3 text-sm font-semibold">
            <p className="flex items-center gap-1 font-bold text-warning"><AlertTriangle size={15} aria-hidden="true" />{T.importErrors}</p>
            <ul className="mt-1 list-disc pl-5 text-fg-2">{importErrors.slice(0, 12).map((e) => <li key={e}>{e}</li>)}</ul>
          </div>
        )}

        <div className="mt-5 overflow-x-auto">
          {items.length === 0 ? <p className="font-semibold text-fg-2">{T.empty}</p> : (
            <table className="w-full min-w-[60rem] text-left text-sm">
              <thead><tr className="text-xs font-bold uppercase tracking-wider text-fg-3">
                <th className="pb-2 pr-3">{T.part}</th><th className="pb-2 pr-3">{T.kind}</th><th className="pb-2 pr-3">{T.month}</th>
                <th className="pb-2 pr-3">{T.replace}</th><th className="w-[34%] pb-2 pr-3">{T.state}</th><th className="pb-2" />
              </tr></thead>
              <tbody>
                {items.map((it) => {
                  const fixed = needsMonth[it.kind] && !RELATIVE.includes(it.month)
                  return (
                    <tr key={it.id} className="border-t-2 border-dashed border-fg/15 align-top">
                      <td className="py-2.5 pr-3">
                        <p className="font-semibold">{it.part || it.fund || it.isin}</p>
                        <p className="text-xs font-semibold text-fg-3">{it.fund && it.part ? `${it.fund} · ` : ''}{it.isin}</p>
                      </td>
                      <td className="py-2.5 pr-3">
                        <select value={it.kind} aria-label={T.kind} onChange={(e) => update(it.id, { kind: e.target.value, month: needsMonth[e.target.value] ? (it.month || 'M-1') : '' })}
                          className="rounded-xl border-2 border-fg bg-card px-2 py-1 font-semibold">
                          {types.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
                        </select>
                      </td>
                      <td className="py-2.5 pr-3">
                        {needsMonth[it.kind] ? (
                          <div className="flex flex-col gap-1">
                            <select value={fixed ? 'fixed' : it.month} aria-label={T.month}
                              onChange={(e) => update(it.id, { month: e.target.value === 'fixed' ? lastMonth() : e.target.value })}
                              className="rounded-xl border-2 border-fg bg-card px-2 py-1 font-semibold">
                              {Object.entries(T.months).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                            </select>
                            {fixed && <input type="month" value={it.month} aria-label={T.month} onChange={(e) => update(it.id, { month: e.target.value })}
                              className="rounded-xl border-2 border-fg bg-card px-2 py-1 font-semibold" />}
                            {it.period_label && <span className="text-xs font-semibold text-fg-3">→ {it.period_label}</span>}
                          </div>
                        ) : <span className="text-fg-3">{T.noMonth}</span>}
                      </td>
                      <td className="py-2.5 pr-3">
                        <input type="checkbox" checked={it.overwrite} title={T.replaceHint} aria-label={T.replaceHint}
                          onChange={(e) => update(it.id, { overwrite: e.target.checked })} className="size-4 accent-[var(--color-magic-500)]" />
                      </td>
                      <td className="py-2.5 pr-3">
                        <Status it={it} preview={previews[it.id]} blocked={!!data.last_run?.blocked} onLink={() => setLinkFor(linkFor === it.id ? null : it.id)} />
                        {linkFor === it.id && <LinkForm item={it} onDone={() => { setLinkFor(null); void test(it) }} />}
                      </td>
                      <td className="py-2.5">
                        <div className="flex gap-1">
                          <button onClick={() => setBrowsing({ isin: it.isin, fund: it.fund, part: it.part })} title={T.seeAvailable} aria-label={T.seeAvailable}
                            className="rounded-full border-2 border-fg/40 p-1.5 hover:border-fg"><Search size={14} /></button>
                          <button onClick={() => test(it)} title={T.test} aria-label={T.test} className="rounded-full border-2 border-fg/40 p-1.5 hover:border-fg"><Wand2 size={14} /></button>
                          <button onClick={() => setLinkFor(linkFor === it.id ? null : it.id)} title={T.haveLink} aria-label={T.haveLink}
                            className="rounded-full border-2 border-fg/40 p-1.5 hover:border-fg"><Link2 size={14} /></button>
                          <button onClick={() => persist(items.filter((x) => x.id !== it.id))} title={T.remove} aria-label={T.remove}
                            className="rounded-full border-2 border-fg/40 p-1.5 hover:border-fg"><Trash2 size={14} /></button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
        <p className="mt-3 text-xs font-semibold text-fg-3">{T.loopHint}</p>
      </section>

      <section className="mt-6 rounded-[var(--radius-card)] border-[2.5px] border-fg bg-sun-400 p-5 shadow-[var(--shadow-pop-lg)]" aria-labelledby="fs-run">
        <h2 id="fs-run" className="text-2xl">{T.step2}</h2>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button size="lg" onClick={runNow} loading={!!runId} disabled={active === 0 || !!runId} icon={<Download size={20} />} className="!bg-card">
            {runId ? T.running : T.runNow(active)}
          </Button>
          <Button onClick={async () => { await flush(); setScheduling(true) }} disabled={active === 0} icon={<CalendarClock size={18} />} className="!bg-card">{T.schedule}</Button>
          <Button onClick={diagnose} loading={diag === 'loading'} icon={<Stethoscope size={18} />} className="!bg-card">{T.diagnostic}</Button>
          {runId && <Link to={`/executions/${runId}`} className="text-sm font-bold underline">{T.details}</Link>}
        </div>
        {data.last_run && !runId && (
          <div className="mt-4 rounded-2xl border-2 border-fg bg-card p-3 text-sm font-semibold">
            {data.last_run.blocked ? (
              <><p className="mb-1 font-bold">{T.blocked}</p><ProblemBox p={data.last_run.blocked} /></>
            ) : (
              <p><span className="text-fg-3">{T.lastRun} ({new Date(data.last_run.at).toLocaleString('fr-FR')}) : </span>{T.summary(counts.ok, counts.present, counts.failed)}</p>
            )}
          </div>
        )}
        {diag && diag !== 'loading' && (
          <div className="mt-4 rounded-2xl border-2 border-fg bg-card p-3">
            <p className="font-display text-lg font-semibold">{T.diagnosticTitle}</p>
            <ul className="mt-1 space-y-1.5 text-sm font-semibold">
              {diag.checks.map((c) => (
                <li key={c.label} className="flex gap-2">
                  {c.ok ? <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-mint-300" aria-hidden="true" /> : <XCircle size={16} className="mt-0.5 shrink-0 text-danger" aria-hidden="true" />}
                  <span><span className="font-bold">{c.label}</span> — {c.message}{c.fix && <span className="block text-fg-2"><span className="font-bold">{T.whatToDo}</span> {c.fix}</span>}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        <p className="mt-3 text-xs font-semibold">{T.destination} : {data.destination} · {T.memory(data.memory.shares, data.memory.funds)}</p>
      </section>

      <details className="mt-6 rounded-[var(--radius-card)] border-2 border-fg/30 p-4">
        <summary className="cursor-pointer font-bold">{T.advanced}</summary>
        <label className="mt-3 inline-flex cursor-pointer items-center gap-2 rounded-full border-2 border-fg/40 px-4 py-2 text-sm font-bold hover:border-fg">
          <Upload size={15} aria-hidden="true" />{T.learnCsv}
          <input type="file" accept=".csv" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) void learn(f); e.target.value = '' }} />
        </label>
      </details>

      <ScheduleDialog open={scheduling} onClose={() => setScheduling(false)} targetType="automation" targetId={AUTOMATION} label={T.scheduleLabel}
        params={{ mode: 'missing' }} />
    </div>
  )
}
