/**
 * Anciens RFI : corpus des précédents, branchement SharePoint (année → RFI → due diligence → final) et inventaire.
 * Lecture seule côté SharePoint ; tout reste sur le poste (data/rfi).
 */
import { useEffect, useState } from 'react'
import { Cloud, FolderOpen, FolderSearch, History, Import, ListChecks, Upload } from 'lucide-react'
import { texts } from '../../content/texts'
import { api, ApiError } from '../../lib/api'
import { useAsync } from '../../lib/hooks'
import type { DueDiligenceList, FinalListing, PrecedentInventory } from '../../lib/types'
import { Button } from '../ui/Button'
import { Field, Select, TextInput } from '../ui/Field'
import { Loading } from '../ui/States'
import { BindingsPanel } from './BindingsPanel'
import { useToast } from '../ui/Toast'

const T = texts.precedents

function FilePick({ label, accept, onFile, busy }: { label: string; accept: string; onFile: (f: File) => void; busy: boolean }) {
  return (
    <label className={`inline-flex cursor-pointer items-center gap-2 rounded-full border-2 border-fg bg-card px-4 py-2 text-sm font-bold transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow-[3px_3px_0_0_var(--color-fg)] ${busy ? 'pointer-events-none opacity-60' : ''}`}>
      <Upload size={15} aria-hidden="true" />{label}
      <input type="file" accept={accept} className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = '' }} />
    </label>
  )
}

function SharePoint({ onImported }: { onImported: () => void }) {
  const toast = useToast()
  const status = useAsync(() => api.rfi.sharepoint.status(), [])
  const [year, setYear] = useState<number | null>(null)
  const [query, setQuery] = useState('')
  const [list, setList] = useState<DueDiligenceList | null>(null)
  const [folder, setFolder] = useState<string | null>(null)
  const [final, setFinal] = useState<FinalListing | null>(null)
  const [fund, setFund] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const ready = status.data?.active != null

  const load = async (y: number | null, q: string) => {
    setBusy(true)
    setError(null)
    setFolder(null)
    setFinal(null)
    try {
      const l = await api.rfi.sharepoint.dueDiligences(y, q)
      setList(l)
      if (!y && l.year) setYear(l.year)
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(String(e)))
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => { if (ready) void load(null, '') }, [ready])

  const pick = async (path: string, f = fund) => {
    setFolder(path)
    setFinal(null)
    try {
      setFinal(await api.rfi.sharepoint.final(path, f))
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(String(e)))
    }
  }

  const importFinal = async () => {
    if (!folder) return
    setBusy(true)
    try {
      const r = await api.rfi.sharepoint.importFinal(folder, fund)
      toast('success', T.imported(r.imported), r.documents.filter((d) => d.identity_problem || d.error).map((d) => `${d.file} : ${d.identity_problem || d.error}`).join(' · ') || undefined)
      onImported()
    } catch (e) {
      toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
    } finally {
      setBusy(false)
    }
  }

  if (status.loading && !status.data) return <Loading compact />
  const s = status.data
  return (
    <div className="rounded-2xl border-2 border-fg bg-card p-4">
      <p className="flex items-center gap-2 font-display text-lg font-semibold"><Cloud size={18} aria-hidden="true" />{T.sharepoint}</p>
      <p className="mt-1 text-xs font-semibold text-fg-3">{s?.site} · {s?.root}</p>
      <p className="mt-2 inline-block rounded-full border-2 border-fg px-2.5 py-0.5 text-xs font-bold">
        {s?.active === 'graph' ? T.spGraph : s?.active === 'local' ? `${T.spLocal} · ${s.local.root}` : T.spNone}
      </p>
      {!ready && <p className="mt-2 text-sm font-semibold text-fg-2">{T.spHelp}</p>}
      {ready && (
        <div className="mt-3 flex flex-col gap-3">
          <div className="grid gap-3 sm:grid-cols-[8rem_minmax(0,1fr)]">
            <Field label={T.year}>
              {({ id }) => (
                <Select id={id} value={year ?? ''} onChange={(e) => { const y = Number(e.target.value) || null; setYear(y); void load(y, '') }}>
                  {(list?.years ?? []).map((y) => <option key={y} value={y}>{y}</option>)}
                </Select>
              )}
            </Field>
            <form onSubmit={(e) => { e.preventDefault(); void load(null, query) }} className="flex items-end gap-2">
              <Field label={T.search}>
                {({ id }) => <TextInput id={id} type="search" value={query} onChange={(e) => setQuery(e.target.value)} />}
              </Field>
              <Button type="submit" size="sm" icon={<FolderSearch size={15} />} loading={busy}>OK</Button>
            </form>
          </div>
          {error && <p role="alert" className="text-sm font-semibold text-danger">{error.message} {error.hint}</p>}
          {list && list.folders.length === 0 && <p className="text-sm font-semibold text-fg-2">{T.noFolder}</p>}
          {list && list.folders.length > 0 && (
            <div>
              {query && list.year && <p className="text-xs font-bold text-magic-300">{T.foundIn(list.year)}</p>}
              <ul className="mt-1 flex max-h-56 flex-col gap-1 overflow-y-auto pr-1">
                {list.folders.map((f) => (
                  <li key={f.path}>
                    <button onClick={() => pick(f.path)} aria-pressed={folder === f.path}
                      className={`flex w-full items-center gap-2 rounded-xl border-2 px-3 py-1.5 text-left text-sm font-semibold ${folder === f.path ? 'border-fg bg-sun-400' : 'border-fg/20 hover:border-fg'}`}>
                      <FolderOpen size={15} aria-hidden="true" />{f.name}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {final && (
            <div className="rounded-xl border-2 border-dashed border-fg/30 p-3">
              <p className="text-sm font-bold">{final.funds.length > 1 ? T.fundsFound(final.funds.length) : `${T.final}${final.final_path ? ` · ${final.final_path}` : ''}`}</p>
              {final.funds.length > 1 && (
                <form onSubmit={(e) => { e.preventDefault(); if (folder) void pick(folder) }} className="mt-2 flex items-end gap-2">
                  <Field label={T.fundFilter}>
                    {({ id }) => <TextInput id={id} type="search" value={fund} onChange={(e) => setFund(e.target.value)} />}
                  </Field>
                  <Button type="submit" size="sm" icon={<FolderSearch size={15} />}>OK</Button>
                </form>
              )}
              {final.hint && <p className="text-sm font-semibold text-fg-2">{final.hint}</p>}
              <ul className="mt-1 text-xs font-semibold text-fg-2">{final.documents.map((d) => <li key={d.path}>📄 {d.fund ? <b>{d.fund} · </b> : null}{d.name}</li>)}</ul>
              {final.documents.length > 0 && (
                <Button className="mt-2" size="sm" variant="primary" icon={<Import size={15} />} loading={busy} onClick={importFinal}>
                  {busy ? T.importing : T.importFinal(final.documents.length)}
                </Button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Inventory({ inv }: { inv: PrecedentInventory }) {
  return (
    <div className="rounded-2xl border-2 border-fg bg-card p-4">
      <p className="flex items-center gap-2 font-display text-lg font-semibold"><ListChecks size={18} aria-hidden="true" />{T.inventory}</p>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl border-2 border-fg bg-mint-400 p-3">
          <p className="text-xs font-bold uppercase tracking-wider">{T.usable}</p>
          <p className="font-display text-3xl font-bold tabular-nums">{inv.usable.total.toLocaleString('fr-FR')}</p>
          <p className="text-xs font-semibold">{Object.entries(inv.usable.by_shape).map(([k, v]) => `${k.toLowerCase()} ${v}`).join(' · ')}</p>
        </div>
        <div className="rounded-xl border-2 border-fg bg-sun-400 p-3">
          <p className="text-xs font-bold uppercase tracking-wider">{T.toReview}</p>
          <ul className="mt-1 text-xs font-semibold">{Object.entries(inv.to_review).map(([k, v]) => <li key={k}>{v} · {k}</li>)}</ul>
        </div>
        <div className="rounded-xl border-2 border-fg bg-card-2 p-3">
          <p className="text-xs font-bold uppercase tracking-wider">{T.uncovered}</p>
          <p className="font-display text-3xl font-bold tabular-nums">{inv.uncovered_total}</p>
          <p className="text-xs font-semibold">{T.coverage(inv.ontology_coverage.auto, inv.ontology_coverage.review, inv.ontology_coverage.none)}</p>
        </div>
      </div>
      <details className="mt-3">
        <summary className="cursor-pointer text-sm font-bold text-magic-300">{T.uncoveredHint(inv.uncovered_total)}</summary>
        <ul className="mt-2 max-h-64 space-y-1 overflow-y-auto pr-1 text-xs font-semibold text-fg-2">
          {inv.uncovered.map((u) => <li key={u.question}><span className="tabular-nums text-fg-3">{T.occurrences(u.occurrences, u.funds)}</span> — {u.question}</li>)}
        </ul>
      </details>
      <ul className="mt-3 list-disc pl-5 text-xs font-semibold text-fg-3">{inv.limits.map((l) => <li key={l}>{l}</li>)}</ul>
    </div>
  )
}

export function PrecedentsPanel() {
  const toast = useToast()
  const stats = useAsync(() => api.rfi.precedents(), [])
  const [inv, setInv] = useState<PrecedentInventory | null>(null)
  const [busy, setBusy] = useState(false)

  const refresh = () => {
    stats.reload()
    api.rfi.inventory().then(setInv).catch(() => setInv(null))
  }
  useEffect(() => { refresh() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const upload = async (fn: () => Promise<{ imported: number }>) => {
    setBusy(true)
    try {
      const r = await fn()
      toast('success', T.imported(r.imported))
      refresh()
    } catch (e) {
      toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
    } finally {
      setBusy(false)
    }
  }

  const s = stats.data
  return (
    <section data-enter className="glass mt-10 rounded-[var(--radius-card)] p-6 sm:p-8">
      <p className="eyebrow"><History size={13} aria-hidden="true" />{T.eyebrow}</p>
      <h2 className="mt-3 text-3xl">{T.title}</h2>
      <p className="mt-2 max-w-3xl font-semibold text-fg-2">{T.lead}</p>
      <div className="mt-5 flex flex-wrap items-center gap-2 text-sm font-bold">
        {s && s.total > 0 ? (
          <>
            <span className="rounded-full border-2 border-fg bg-mint-400 px-3 py-0.5">{T.entries(s.total)}</span>
            <span className="rounded-full border-2 border-fg bg-card px-3 py-0.5">{T.sources(s.sources)}</span>
            {s.blocked > 0 && <span className="rounded-full border-2 border-fg bg-bubble-400 px-3 py-0.5 text-white">{T.blockedCount(s.blocked)}</span>}
          </>
        ) : <span className="text-fg-2">{T.empty}</span>}
      </div>
      <div className="mt-4 flex flex-wrap gap-3">
        <FilePick label={T.wording} accept=".json,.zip" busy={busy} onFile={(f) => upload(() => api.rfi.importWording(f))} />
        <FilePick label={T.document} accept=".xlsx,.xlsm,.docx" busy={busy} onFile={(f) => upload(() => api.rfi.importPrecedent(f))} />
      </div>
      <p className="mt-2 text-xs font-semibold text-fg-3">{T.wordingHint}</p>
      <div className="mt-5 grid items-start gap-5 lg:grid-cols-2">
        <SharePoint onImported={refresh} />
        {inv && inv.total > 0 && <Inventory inv={inv} />}
        <BindingsPanel />
      </div>
    </section>
  )
}
