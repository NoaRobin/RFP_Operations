/**
 * Merlin · Atelier Excel : une grille par ISIN (ISIN sur le côté, questions en haut, ou l'inverse), remplie par le
 * moteur du compléteur RFI. Chaque case : compréhension de l'en-tête (FR / EN / ES / IT, période, unité, format de la
 * cellule), données Fabric de SA part et de son fonds, DIC / prospectus, anciens RFI, Qvidian ; les réponses possibles
 * sont classées (merlin/rfi/aggregate.py). Le fichier rendu est le même, au même format, seules les cases réponse
 * changent (merlin/rfi/writer.py) ; l'original n'est jamais modifié.
 */
import { useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Check, Download, FileSpreadsheet, FlaskConical, RotateCcw, Table2, Wand2 } from 'lucide-react'
import { Dropzone } from '../components/atelier/Dropzone'
import { CellPanel } from '../components/atelier/grid/CellPanel'
import { IsinRail } from '../components/atelier/grid/IsinRail'
import { Matrix } from '../components/atelier/grid/Matrix'
import { buildGrids, statesOf, type GridColumn } from '../components/atelier/grid/model'
import type { Override } from '../components/rfi/review/state'
import { STATE_DOT } from '../components/rfi/review/state'
import { Button } from '../components/ui/Button'
import { Select, Switch, TextInput } from '../components/ui/Field'
import { ErrorState, Loading } from '../components/ui/States'
import { useToast } from '../components/ui/Toast'
import { texts } from '../content/texts'
import { api, ApiError } from '../lib/api'
import { formatRelative, todayIso } from '../lib/format'
import { useAsync } from '../lib/hooks'
import type { RfiAnalysis, RfiDocument, RfiGenerated, RfiLanguage, RfiRequest } from '../lib/types'
import { gsap, useGSAP } from '../motion/gsap'
import { d, ease, prefersReducedMotion } from '../motion/tokens'

const G = texts.grid
const ACCEPT = '.xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

export default function Atelier() {
  const toast = useToast()
  const root = useRef<HTMLDivElement>(null)
  const recent = useAsync(() => api.rfi.documents(), [])
  const factsQuery = useAsync(() => api.rfi.facts(), [])
  const [doc, setDoc] = useState<RfiDocument | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [asOf, setAsOf] = useState(todayIso())
  const [language, setLanguage] = useState<RfiLanguage>('fr')
  const [useQvidian, setUseQvidian] = useState(true)
  const [overwrite, setOverwrite] = useState(false)
  const [highlight, setHighlight] = useState(true)
  const [overrides, setOverrides] = useState<Record<string, Override>>({})
  const [accepted, setAccepted] = useState<Set<string>>(new Set())
  const [analysis, setAnalysis] = useState<RfiAnalysis | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [result, setResult] = useState<RfiGenerated | null>(null)
  const [sheet, setSheet] = useState(0)
  const [selected, setSelected] = useState<string | null>(null)
  const [isinQuery, setIsinQuery] = useState('')
  const [focus, setFocus] = useState<string | null>(null)
  const [onlyTodo, setOnlyTodo] = useState(false)
  const seq = useRef(0)

  useGSAP(() => {
    if (prefersReducedMotion()) return
    gsap.from('[data-enter]', { y: 24, opacity: 0, stagger: 0.06, duration: d('slow'), ease: ease.out })
  }, { scope: root, dependencies: [doc?.id ?? 'home'] })

  const request = (extra: Partial<RfiRequest> = {}): RfiRequest => ({
    pid: null, isin: null, as_of: asOf, language, overrides, overwrite, accept: [...accepted], use_qvidian: useQvidian,
    highlight_missing: highlight, ...extra,
  })

  const run = async (target: RfiDocument, extra: Partial<RfiRequest>, fresh: boolean) => {
    const n = ++seq.current
    if (fresh) setAnalyzing(true)
    setResult(null)
    try {
      const a = await api.rfi.answers(target.id, request({ fresh, ...extra }))
      if (n === seq.current) setAnalysis(a)
    } catch (e) {
      toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
    } finally {
      if (n === seq.current) setAnalyzing(false)
    }
  }

  const open = async (loader: Promise<RfiDocument>) => {
    setBusy(true); setError(null); setAnalysis(null); setResult(null); setOverrides({}); setAccepted(new Set()); setSelected(null); setSheet(0); setFocus(null)
    try {
      const d0 = await loader
      setDoc(d0)
      setLanguage(d0.language ?? 'fr')
      recent.reload()
      void run(d0, { language: d0.language ?? 'fr', overrides: {}, accept: [] }, true)
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(String(e)))
    } finally {
      setBusy(false)
    }
  }

  const { grids, others } = useMemo(() => analysis && doc ? buildGrids(analysis, doc.shares ?? []) : { grids: [], others: [] }, [analysis, doc])
  const states = useMemo(() => analysis ? statesOf(analysis, accepted, overrides) : {}, [analysis, accepted, overrides])
  const grid = grids[Math.min(sheet, Math.max(0, grids.length - 1))]
  const byId = useMemo(() => Object.fromEntries((analysis?.questions ?? []).map((q) => [q.id, q])), [analysis])
  const rows = useMemo(() => {
    if (!grid) return []
    const q = isinQuery.trim().toLowerCase()
    return grid.rows.filter((r) => (!focus || r.isin === focus)
      && (!q || `${r.isin} ${r.share?.fund ?? ''} ${r.share?.share_name ?? ''}`.toLowerCase().includes(q))
      && (!onlyTodo || Object.values(r.cells).some((c) => states[c.id] === 'review' || states[c.id] === 'none')))
  }, [grid, isinQuery, focus, onlyTodo, states])
  const counts = useMemo(() => {
    const c: Record<string, number> = { auto: 0, accepted: 0, review: 0, none: 0, skipped: 0, existing: 0 }
    Object.values(states).forEach((s) => { c[s] += 1 })
    return c
  }, [states])
  const pending = (analysis?.questions ?? []).filter((q) => states[q.id] === 'review').map((q) => q.id)

  const applyOverrides = (next: Record<string, Override>, changed: string[], text?: string) => {
    setOverrides(next)
    setResult(null)
    if (analysis && text !== undefined) {  // affichage immédiat ; le serveur confirme en arrière-plan (cache des cases)
      setAnalysis({ ...analysis, questions: analysis.questions.map((q) => (changed.includes(q.id) ? { ...q, answer: text } : q)) })
    }
    if (doc) void run(doc, { overrides: next }, false)
  }
  const setOverride = (id: string, value: Override | undefined) => {
    const next = { ...overrides }
    if (value === undefined) delete next[id]
    else next[id] = value
    applyOverrides(next, [id], value && typeof value === 'object' ? value.text : undefined)
  }
  const acceptIds = (ids: string[], on = true) => {
    const next = new Set(accepted)
    ids.forEach((id) => (on ? next.add(id) : next.delete(id)))
    setAccepted(next)
    setResult(null)
  }
  const onColumn = (col: GridColumn, action: 'accept' | 'skip' | 'reset' | { concept: string }) => {
    if (action === 'accept') { acceptIds(col.ids.filter((id) => states[id] === 'review')); return }
    const next = { ...overrides }
    col.ids.forEach((id) => {
      if (action === 'reset') delete next[id]
      else next[id] = action === 'skip' ? null : action.concept
    })
    applyOverrides(next, col.ids)
  }
  const nextTodo = (from: string) => {
    if (!grid) return
    const order = rows.flatMap((r) => grid.columns.map((c) => r.cells[c.key]?.id).filter(Boolean) as string[])
    const i = order.indexOf(from)
    for (let k = 1; k <= order.length; k++) {
      const id = order[(i + k) % order.length]
      if (states[id] === 'review' || states[id] === 'none') { setSelected(id); return }
    }
  }

  const generate = async () => {
    if (!doc) return
    setGenerating(true)
    try {
      const r = await api.rfi.generate(doc.id, request())
      setResult(r)
      window.dispatchEvent(new Event('rfp:shower'))
      toast('success', G.done(r.written, r.version))
    } catch (e) {
      toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
    } finally {
      setGenerating(false)
    }
  }

  const q = selected ? byId[selected] ?? null : null
  const qRow = q && grid ? grid.rows.find((r) => Object.values(r.cells).some((c) => c.id === q.id)) ?? null : null
  const toWrite = counts.auto + counts.accepted + (overwrite ? counts.existing : 0)

  return (
    <div ref={root} className={`mx-auto pt-10 sm:pt-14 ${doc ? 'w-[min(100%-1.5rem,150rem)]' : 'w-[min(100%-2rem,82rem)]'}`}>
      <header data-enter className="max-w-4xl">
        <p className="eyebrow"><Table2 size={13} aria-hidden="true" />{G.eyebrow}</p>
        <h1 className={`mt-4 font-bold ${doc ? 'text-[clamp(2rem,4vw,3rem)]' : 'text-[clamp(2.4rem,6vw,4.5rem)]'}`}>{G.title}</h1>
        {!doc && <p className="mt-4 text-lg font-semibold text-fg-2">{G.lead}</p>}
      </header>

      {!doc && (
        <div className="mt-10 grid gap-8 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          <div data-enter className="flex flex-col gap-4">
            <Dropzone onFile={(f) => open(api.rfi.upload(f))} busy={busy} accept={ACCEPT}
              title={G.drop} body={G.dropHint} activeTitle={G.dropActive} busyTitle={G.reading} />
            <div className="flex flex-wrap gap-3">
              <Button onClick={() => open(api.rfi.demo('grid'))} disabled={busy} icon={<FlaskConical size={18} />}>{G.demo}</Button>
              <Link to="/atelier/fonds" className="inline-flex items-center gap-2 rounded-full border-2 border-fg/40 px-4 py-2 text-sm font-bold hover:border-fg">{G.fundSheet}<ArrowRight size={14} /></Link>
              <Link to="/atelier/recettes" className="inline-flex items-center gap-2 rounded-full border-2 border-fg/40 px-4 py-2 text-sm font-bold hover:border-fg">{G.recipes}<ArrowRight size={14} /></Link>
            </div>
            {error && <ErrorState error={error} />}
          </div>
          <aside data-enter className="glass rounded-[var(--radius-card)] p-6">
            <h2 className="text-2xl">{G.recent}</h2>
            {recent.loading && !recent.data && <Loading compact />}
            {(() => {
              const list = (recent.data ?? []).filter((r) => r.suffix !== '.docx').slice(0, 8)
              if (recent.data && !list.length) return <p className="mt-3 text-fg-2">{G.noRecent}</p>
              return (
                <ul className="mt-4 flex flex-col gap-2">
                  {list.map((r) => (
                    <li key={r.id}>
                      <button onClick={() => open(api.rfi.document(r.id))} disabled={busy}
                        className="flex w-full items-center gap-3 rounded-xl border-2 border-fg bg-card px-3 py-2 text-left transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow-[3px_3px_0_0_var(--color-fg)]">
                        <FileSpreadsheet size={18} aria-hidden="true" className="text-mint-500" />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate font-semibold">{r.filename}</span>
                          <span className="text-xs font-semibold text-fg-3">{r.user} · {formatRelative(r.uploaded_at)}</span>
                        </span>
                        <ArrowRight size={16} aria-hidden="true" />
                      </button>
                    </li>
                  ))}
                </ul>
              )
            })()}
          </aside>
        </div>
      )}

      {doc && (
        <>
          <section data-enter className="mt-6 flex flex-col gap-4 rounded-[var(--radius-card)] border-[2.5px] border-fg bg-card p-4 shadow-[4px_4px_0_0_var(--color-fg)]">
            <div className="flex flex-wrap items-center gap-3">
              <span className="grid size-11 place-items-center rounded-2xl border-[2.5px] border-fg bg-sun-400"><FileSpreadsheet size={22} aria-hidden="true" /></span>
              <div className="min-w-0 flex-1">
                <p className="truncate font-display text-xl font-semibold">{doc.filename}</p>
                <p className="text-sm font-semibold text-fg-2">
                  {grids.map((g) => `${g.sheet} : ${g.rows.length} ISIN × ${g.columns.length} questions`).join(' · ') || (analysis ? G.noGrid : G.analyzing)}
                </p>
              </div>
              <Button variant="ghost" size="sm" icon={<RotateCcw size={15} />} onClick={() => { setDoc(null); setAnalysis(null); setResult(null) }}>{G.another}</Button>
            </div>
            <div className="flex flex-wrap items-end gap-4">
              <label className="text-xs font-bold text-fg-2">{G.asOf}
                <TextInput type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} className="mt-1 h-10 w-44" />
              </label>
              <label className="text-xs font-bold text-fg-2">{G.language}
                <Select value={language} onChange={(e) => setLanguage(e.target.value as RfiLanguage)} className="mt-1 h-10 w-40">
                  {(['fr', 'en', 'es', 'it'] as RfiLanguage[]).map((l) => <option key={l} value={l}>{texts.rfi.languages[l] ?? l}</option>)}
                </Select>
              </label>
              <div className="shrink-0 pb-2"><Switch checked={useQvidian} onChange={setUseQvidian} label={G.qvidian} /></div>
              <div className="shrink-0 pb-2"><Switch checked={overwrite} onChange={(v) => { setOverwrite(v); setResult(null) }} label={G.overwrite} /></div>
              <div className="shrink-0 pb-2"><Switch checked={highlight} onChange={(v) => { setHighlight(v); setResult(null) }} label={G.highlight} /></div>
              <span className="ml-auto flex flex-wrap gap-2">
                <Button variant="ghost" icon={<Wand2 size={16} />} disabled={analyzing} onClick={() => doc && run(doc, {}, true)}>{G.analyze}</Button>
                {pending.length > 0 && <Button icon={<Check size={16} />} onClick={() => acceptIds(pending)}>{G.acceptAll(pending.length)}</Button>}
                <Button variant="primary" icon={<Download size={16} />} disabled={!analysis || generating || analyzing || toWrite === 0} onClick={generate}>
                  {generating ? G.generating : `${G.download} (${toWrite})`}
                </Button>
              </span>
            </div>
            {analysis && (
              <div className="flex flex-wrap items-center gap-2 text-xs font-bold" aria-live="polite">
                {(['auto', 'accepted', 'review', 'none', 'existing', 'skipped'] as const).filter((k) => counts[k]).map((k) => (
                  <span key={k} className="inline-flex items-center gap-1.5 rounded-full border-2 border-fg/20 px-2.5 py-0.5">
                    <span className={`size-2 rounded-full ${STATE_DOT[k]}`} aria-hidden="true" />{G.states[k]} {counts[k]}
                  </span>
                ))}
                <label className="ml-auto inline-flex items-center gap-2"><input type="checkbox" checked={onlyTodo} onChange={(e) => setOnlyTodo(e.target.checked)} className="size-4 accent-[var(--color-magic-500)]" />{G.onlyTodo}</label>
              </div>
            )}
            {result && (
              <div role="status" className="flex flex-wrap items-center gap-3 rounded-2xl border-2 border-fg bg-mint-400/30 px-4 py-3">
                <Check size={18} aria-hidden="true" />
                <span className="font-semibold">{G.done(result.written, result.version)}{result.to_ask?.length ? ` · ${G.toAsk(result.to_ask.length)}` : ''}</span>
                <a href={result.download} className="ml-auto inline-flex items-center gap-2 rounded-full border-2 border-fg bg-fg px-4 py-1.5 text-sm font-bold text-canvas"><Download size={15} />{G.downloadAgain}</a>
              </div>
            )}
            {analysis?.errors && analysis.errors.length > 0 && (
              <details className="text-xs font-semibold text-fg-2"><summary className="cursor-pointer">{analysis.errors.length} alerte(s) de lecture</summary>
                <ul className="mt-1 list-disc pl-5">{analysis.errors.slice(0, 20).map((e) => <li key={e}>{e}</li>)}</ul></details>
            )}
          </section>

          {analyzing && !analysis && <div className="mt-8"><Loading /></div>}
          {analysis && !grid && <p className="mt-8 rounded-2xl border-2 border-fg bg-card p-5 font-semibold">{G.noGrid} {G.openInRfi}</p>}

          {grid && (
            <>
              {grids.length > 1 && (
                <div className="mt-5 flex flex-wrap gap-2" role="tablist" aria-label="Feuilles">
                  {grids.map((g, i) => (
                    <button key={g.sheet} role="tab" aria-selected={i === sheet} onClick={() => { setSheet(i); setSelected(null); setFocus(null) }}
                      className={`rounded-full border-2 border-fg px-4 py-1.5 text-sm font-bold ${i === sheet ? 'bg-fg text-canvas' : 'bg-card hover:bg-card-2'}`}>{g.sheet}</button>
                  ))}
                </div>
              )}
              <div className={`mt-5 grid gap-4 ${q ? 'lg:grid-cols-[17rem_minmax(0,1fr)] xl:grid-cols-[17rem_minmax(0,1fr)_26rem]' : 'lg:grid-cols-[17rem_minmax(0,1fr)]'} ${analyzing ? 'opacity-60' : ''}`}>
                <IsinRail grid={grid} states={states} query={isinQuery} onQuery={setIsinQuery} focus={focus} onFocus={setFocus} />
                <div className="min-w-0">
                  <Matrix grid={grid} states={states} rows={rows} selected={selected} onSelect={setSelected} facts={factsQuery.data ?? []} onColumn={onColumn}
                    onKey={(k) => {
                      if (!selected) return
                      if (k === 'accept' && states[selected] === 'review') { acceptIds([selected]); nextTodo(selected) }
                      if (k === 'skip') setOverride(selected, null)
                    }} />
                  {others.length > 0 && <p className="mt-3 text-xs font-semibold text-fg-3">{G.others(others.length)}</p>}
                </div>
                {q && (
                  <div className="lg:col-span-2 xl:col-span-1">
                    <CellPanel q={q} row={qRow} state={states[q.id] ?? null} override={overrides[q.id]}
                      onOverride={(v) => setOverride(q.id, v)} onAccept={() => { acceptIds([q.id]); nextTodo(q.id) }} onClose={() => setSelected(null)} />
                  </div>
                )}
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
