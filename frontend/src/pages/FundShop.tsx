/**
 * Documents des fonds : la « liste de courses » des PDF du site (DIC, prospectus, reportings, SFDR), à lancer tout de
 * suite ou à programmer (mois relatifs pour la boucle). Le téléchargement est une automatisation : journal en direct.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { CalendarClock, Download, FileSpreadsheet, FileText, Plus, Save, Search, Trash2, Upload, Wand2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { ScheduleDialog } from '../components/ScheduleDialog'
import { Button } from '../components/ui/Button'
import { ErrorState, Loading } from '../components/ui/States'
import { useToast } from '../components/ui/Toast'
import { texts } from '../content/texts'
import { api, ApiError } from '../lib/api'
import type { FundEntry, FundShopItem, FundShopOverview } from '../lib/types'
import { gsap, useGSAP } from '../motion/gsap'
import { d, ease, prefersReducedMotion } from '../motion/tokens'

const T = texts.fundshop
const AUTOMATION = 'telechargement_documents'

function monthMode(month: string): string {
  return month === 'M-1' || month === 'M-2' ? month : 'fixed'
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

export default function FundShop() {
  const toast = useToast()
  const navigate = useNavigate()
  const root = useRef<HTMLDivElement>(null)
  const [data, setData] = useState<FundShopOverview | null>(null)
  const [items, setItems] = useState<FundShopItem[]>([])
  const [error, setError] = useState<ApiError | null>(null)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [scheduling, setScheduling] = useState(false)
  const [tests, setTests] = useState<Record<string, string>>({})

  const load = (o: FundShopOverview) => { setData(o); setItems(o.items); setDirty(false) }
  useEffect(() => { api.fundshop.overview().then(load).catch((e) => setError(e)) }, [])
  useGSAP(() => {
    if (prefersReducedMotion() || !data) return
    gsap.from('[data-enter]', { y: 24, opacity: 0, stagger: 0.06, duration: d('slow'), ease: ease.out })
  }, { scope: root, dependencies: [!!data] })

  const types = data?.types ?? []
  const needsMonth = useMemo(() => Object.fromEntries(types.map((t) => [t.key, t.needs_month])), [types])
  const update = (id: string, patch: Partial<FundShopItem>) => { setItems((xs) => xs.map((x) => (x.id === id ? { ...x, ...patch } : x))); setDirty(true) }
  const add = (fund: string, part: string, isin: string) => {
    setItems((xs) => [...xs, { id: `new-${Date.now()}`, isin, fund, part, kind: 'dic', month: '', filename: '', active: true, overwrite: false }])
    setDirty(true)
  }
  const save = async () => {
    setBusy(true)
    try {
      load(await api.fundshop.save(items.map(({ target, period_label, present, error: _e, ...rest }) => ({ ...rest, id: rest.id.startsWith('new-') ? undefined : rest.id }))))
      toast('success', T.saved)
      return true
    } catch (e) {
      toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
      return false
    } finally { setBusy(false) }
  }
  const runNow = async () => {
    if (dirty && !(await save())) return
    const run = await api.run(AUTOMATION, { mode: 'missing', navigateur: true })
    navigate(`/executions/${run.id}`)
  }
  const importFile = async (file: File) => {
    setBusy(true)
    try {
      const o = await api.fundshop.importExcel(file)
      load(o)
      toast('success', T.imported(o.imported ?? 0), (o.errors ?? []).slice(0, 4).join(' · ') || undefined)
    } catch (e) {
      toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
    } finally { setBusy(false) }
  }
  const learn = async (file: File) => {
    const r = await api.fundshop.learnCsv(file)
    toast('success', `${r.learned} adresses apprises`)
    load(await api.fundshop.overview())
  }
  const test = async (it: FundShopItem) => {
    setTests((t) => ({ ...t, [it.id]: T.testing }))
    try {
      const r = await api.fundshop.tryOne(it.isin, it.kind, it.month)
      setTests((t) => ({ ...t, [it.id]: r.found ? T.found(r.strategy ?? '') : T.notFound }))
    } catch {
      setTests((t) => ({ ...t, [it.id]: T.notFound }))
    }
  }

  if (error) return <div className="mx-auto w-[min(100%-2rem,82rem)] pt-14"><ErrorState error={error} /></div>
  if (!data) return <Loading />
  return (
    <div ref={root} className="mx-auto w-[min(100%-2rem,82rem)] pt-10 sm:pt-14">
      <header data-enter className="max-w-3xl">
        <p className="eyebrow"><FileText size={13} aria-hidden="true" />{T.eyebrow}</p>
        <h1 className="mt-4 text-[clamp(2.2rem,5.5vw,4rem)] font-bold">{T.title}</h1>
        <p className="mt-4 text-lg font-semibold text-fg-2">{T.lead}</p>
      </header>

      <section data-enter className="glass mt-8 rounded-[var(--radius-card)] p-5 sm:p-7">
        <div className="flex flex-wrap items-center gap-3">
          <FundSearch onPick={add} />
          <label className={`inline-flex cursor-pointer items-center gap-2 rounded-full border-2 border-fg bg-card px-4 py-2 text-sm font-bold ${busy ? 'pointer-events-none opacity-60' : ''}`}>
            <FileSpreadsheet size={15} aria-hidden="true" />{T.importExcel}
            <input type="file" accept=".xlsx,.xlsm" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) void importFile(f); e.target.value = '' }} />
          </label>
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-full border-2 border-fg/40 px-4 py-2 text-sm font-bold">
            <Upload size={15} aria-hidden="true" />{T.learnCsv}
            <input type="file" accept=".csv" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) void learn(f); e.target.value = '' }} />
          </label>
        </div>
        <p className="mt-2 text-xs font-semibold text-fg-3">{T.destination} : {data.destination} · {T.memory(data.memory.shares, data.memory.funds)}</p>

        <div className="mt-5 overflow-x-auto">
          {items.length === 0 ? <p className="font-semibold text-fg-2">{T.empty}</p> : (
            <table className="w-full min-w-[58rem] text-left text-sm">
              <thead><tr className="text-xs font-bold uppercase tracking-wider text-fg-3">
                <th className="pb-2 pr-3">{T.fund}</th><th className="pb-2 pr-3">{T.kind}</th><th className="pb-2 pr-3">{T.month}</th>
                <th className="pb-2 pr-3">{T.name}</th><th className="pb-2 pr-3">{T.active}</th><th className="pb-2" />
              </tr></thead>
              <tbody>
                {items.map((it) => {
                  const mode = monthMode(it.month)
                  return (
                    <tr key={it.id} className={`border-t-2 border-dashed border-fg/15 align-top ${it.active ? '' : 'opacity-50'}`}>
                      <td className="py-2 pr-3">
                        <p className="font-semibold">{it.fund || it.isin}</p>
                        <p className="text-xs font-semibold text-fg-3">{it.part} · {it.isin}</p>
                        {it.target && <p className={`mt-0.5 text-[0.7rem] font-bold ${it.present ? 'text-mint-300' : 'text-fg-3'}`}>{it.present ? `✓ ${T.present}` : T.missing}</p>}
                      </td>
                      <td className="py-2 pr-3">
                        <select value={it.kind} onChange={(e) => update(it.id, { kind: e.target.value, month: needsMonth[e.target.value] ? (it.month || 'M-1') : '' })}
                          className="rounded-xl border-2 border-fg bg-card px-2 py-1 font-semibold">
                          {types.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
                        </select>
                      </td>
                      <td className="py-2 pr-3">
                        {needsMonth[it.kind] ? (
                          <div className="flex flex-col gap-1">
                            <select value={mode} onChange={(e) => update(it.id, { month: e.target.value === 'fixed' ? new Date(new Date().getFullYear(), new Date().getMonth() - 1, 15).toISOString().slice(0, 7) : e.target.value })}
                              className="rounded-xl border-2 border-fg bg-card px-2 py-1 font-semibold">
                              {Object.entries(T.monthModes).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                            </select>
                            {mode === 'fixed' && <input type="month" value={it.month} onChange={(e) => update(it.id, { month: e.target.value })} className="rounded-xl border-2 border-fg bg-card px-2 py-1 font-semibold" />}
                            {it.period_label && <span className="text-xs font-semibold text-fg-3">→ {it.period_label}</span>}
                          </div>
                        ) : <span className="text-xs font-semibold text-fg-3">{T.noMonth}</span>}
                      </td>
                      <td className="py-2 pr-3">
                        <input value={it.filename} onChange={(e) => update(it.id, { filename: e.target.value })} placeholder={T.namePlaceholder}
                          className="w-full min-w-[14rem] rounded-xl border-2 border-fg bg-card px-2 py-1 font-semibold" />
                        <p className="mt-0.5 truncate text-[0.7rem] font-semibold text-fg-3" title={it.target}>{it.target}</p>
                        {tests[it.id] && <p className="text-[0.7rem] font-bold text-magic-300">{tests[it.id]}</p>}
                      </td>
                      <td className="py-2 pr-3">
                        <label className="flex items-center gap-1.5 text-xs font-semibold"><input type="checkbox" checked={it.active} onChange={(e) => update(it.id, { active: e.target.checked })} className="accent-[var(--color-magic-500)]" />{T.active}</label>
                        <label className="mt-1 flex items-center gap-1.5 text-xs font-semibold"><input type="checkbox" checked={it.overwrite} onChange={(e) => update(it.id, { overwrite: e.target.checked })} className="accent-[var(--color-magic-500)]" />{T.overwrite}</label>
                      </td>
                      <td className="py-2">
                        <div className="flex gap-1">
                          <button onClick={() => test(it)} title={T.test} aria-label={T.test} className="rounded-full border-2 border-fg/40 p-1.5 hover:border-fg"><Wand2 size={14} /></button>
                          <button onClick={() => { setItems((xs) => xs.filter((x) => x.id !== it.id)); setDirty(true) }} title={T.remove} aria-label={T.remove}
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

      <section data-enter className="mt-6 flex flex-wrap items-center gap-3 rounded-[var(--radius-card)] border-[2.5px] border-fg bg-sun-400 p-5 shadow-[var(--shadow-pop-lg)]">
        <Button onClick={save} loading={busy} disabled={!dirty} icon={<Save size={18} />} className="!bg-card">{T.save}</Button>
        <Button size="lg" onClick={runNow} disabled={items.length === 0} icon={<Download size={20} />} className="!bg-card">{T.runNow}</Button>
        <Button onClick={async () => { if (!dirty || (await save())) setScheduling(true) }} disabled={items.length === 0} icon={<CalendarClock size={18} />} className="!bg-card">{T.schedule}</Button>
        <span className="ml-auto inline-flex items-center gap-1 text-sm font-bold"><Plus size={14} aria-hidden="true" />{items.length} document{items.length > 1 ? 's' : ''}</span>
      </section>
      <ScheduleDialog open={scheduling} onClose={() => setScheduling(false)} targetType="automation" targetId={AUTOMATION} label={T.scheduleLabel}
        params={{ mode: 'missing', navigateur: true }} />
    </div>
  )
}
