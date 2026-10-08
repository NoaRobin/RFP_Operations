/**
 * Remplir un RFI : déposer un Excel ou un Word, choisir le fonds, vérifier les réponses trouvées dans Fabric,
 * télécharger le même fichier avec les cases quantitatives remplies. L'original n'est jamais modifié.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowRight, Check, Download, FileQuestion, FileSpreadsheet, FileText, RotateCcw, Search, Sparkles, Wand2 } from 'lucide-react'
import { Dropzone } from '../components/atelier/Dropzone'
import { Button } from '../components/ui/Button'
import { Field, Select, Switch, TextInput } from '../components/ui/Field'
import { EmptyState, ErrorState, Loading } from '../components/ui/States'
import { useToast } from '../components/ui/Toast'
import { texts } from '../content/texts'
import { api, ApiError } from '../lib/api'
import { formatRelative, todayIso } from '../lib/format'
import { useAsync } from '../lib/hooks'
import type { FundEntry, RfiAnalysis, RfiDocument, RfiFact, RfiGenerated, RfiQuestion, RfiRequest, RfiStatus } from '../lib/types'
import { gsap, useGSAP } from '../motion/gsap'
import { d, ease, prefersReducedMotion } from '../motion/tokens'

const ACCEPT = '.xlsx,.xlsm,.docx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.openxmlformats-officedocument.wordprocessingml.document'
const AUTO = '__auto__'
const SKIP = '__skip__'

const STATUS_STYLE: Record<RfiStatus, string> = {
  fill: 'bg-mint-400',
  existing: 'bg-card-3',
  no_value: 'bg-[#ffd6dc]',
  unmatched: 'bg-card',
  skipped: 'bg-card',
}

type Filter = 'todo' | 'all' | 'unmatched'

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = value >= 0.8 ? 'bg-mint-400' : value >= 0.55 ? 'bg-sun-400' : 'bg-bubble-400'
  return (
    <span className="inline-flex items-center gap-2" title={`${pct} %`}>
      <span className="relative h-2.5 w-16 overflow-hidden rounded-full border-2 border-fg bg-card">
        <span className={`absolute inset-y-0 left-0 ${color}`} style={{ width: `${pct}%` }} />
      </span>
      <span className="text-xs font-bold tabular-nums text-fg-2">{pct}%</span>
    </span>
  )
}

/** Choix du fonds et de la part : suggestions issues du document + recherche dans l'annuaire Fabric. */
function FundPicker({ doc, pid, isin, onPick }: { doc: RfiDocument; pid: string | null; isin: string | null; onPick: (pid: string, isin: string | null) => void }) {
  const [query, setQuery] = useState('')
  const [funds, setFunds] = useState<FundEntry[]>([])
  const [error, setError] = useState<ApiError | null>(null)

  useEffect(() => {
    let alive = true
    const id = window.setTimeout(() => {
      api.rfi.funds(query).then((f) => alive && setFunds(f)).catch((e) => alive && setError(e))
    }, 200)
    return () => {
      alive = false
      window.clearTimeout(id)
    }
  }, [query])

  const current = funds.find((f) => f.pid === pid)
  return (
    <div className="flex flex-col gap-4">
      {doc.suggestions && doc.suggestions.length > 0 ? (
        <div>
          <p className="text-sm font-bold text-fg-2">{texts.rfi.suggestions}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {doc.suggestions.map((s) => {
              const active = s.pid === pid && (s.isin ?? null) === (isin ?? null)
              return (
                <button key={`${s.pid}-${s.isin}`} onClick={() => onPick(s.pid, s.isin)} title={s.reason}
                  className={`flex flex-col items-start rounded-2xl border-[2.5px] border-fg px-4 py-2 text-left transition-[transform,box-shadow] hover:-translate-y-0.5 ${active ? 'bg-sun-400 shadow-[3px_3px_0_0_var(--color-fg)]' : 'bg-card hover:shadow-[3px_3px_0_0_var(--color-fg)]'}`}>
                  <span className="font-display font-semibold">{s.share_name ?? s.name}</span>
                  <span className="text-xs font-semibold text-fg-2">{s.isin ?? s.pid} · {s.reason}</span>
                </button>
              )
            })}
          </div>
        </div>
      ) : (
        <p className="text-sm font-semibold text-fg-2">{texts.rfi.noSuggestion}</p>
      )}
      <div className="relative">
        <label htmlFor="fund-search" className="sr-only">{texts.rfi.fundSearch}</label>
        <Search className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-fg-3" size={17} aria-hidden="true" />
        <TextInput id="fund-search" type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={texts.rfi.fundSearch} className="pl-10" />
      </div>
      {error && <p role="alert" className="text-sm text-danger">{error.message} {error.hint}</p>}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={texts.rfi.fund}>
          {({ id }) => (
            <Select id={id} value={pid ?? ''} onChange={(e) => {
              const f = funds.find((x) => x.pid === e.target.value)
              if (f) onPick(f.pid, f.shares[0]?.isin ?? null)
            }}>
              <option value="" disabled>{texts.automation.selectPlaceholder}</option>
              {pid && !current && <option value={pid}>{doc.suggestions?.find((s) => s.pid === pid)?.name ?? pid}</option>}
              {funds.map((f) => <option key={f.pid} value={f.pid}>{f.name}</option>)}
            </Select>
          )}
        </Field>
        <Field label={texts.rfi.share}>
          {({ id }) => (
            <Select id={id} value={isin ?? ''} disabled={!pid} onChange={(e) => pid && onPick(pid, e.target.value || null)}>
              <option value="">—</option>
              {isin && !current?.shares.some((s) => s.isin === isin) && <option value={isin}>{isin}</option>}
              {current?.shares.map((s) => <option key={s.isin} value={s.isin}>{s.name} · {s.isin}</option>)}
            </Select>
          )}
        </Field>
      </div>
    </div>
  )
}

function QuestionRow({ q, facts, override, onOverride }: {
  q: RfiQuestion; facts: RfiFact[]; override: string | null | undefined; onOverride: (value: string | null | undefined) => void
}) {
  const selectValue = override === undefined ? AUTO : override === null ? SKIP : override
  return (
    <tr data-row className="border-t-2 border-dashed border-fg/15 align-top">
      <td className="py-3 pr-4">
        <p className="font-semibold text-fg">{q.text}</p>
        <p className="mt-0.5 text-xs font-semibold text-fg-3">{q.location}{q.context ? ` · ${q.context}` : ''}</p>
      </td>
      <td className="py-3 pr-4">
        {q.answer ? (
          <p className={`font-display text-lg font-semibold ${q.status === 'existing' ? 'text-fg-3 line-through decoration-2' : 'text-fg'}`}>{q.answer}</p>
        ) : (
          <p className="text-fg-3">{texts.rfi.noAnswer}</p>
        )}
        {q.status === 'existing' && q.existing && <p className="text-xs font-semibold text-fg-2">Déjà : {q.existing}</p>}
      </td>
      <td className="py-3 pr-4 min-w-[13rem]">
        <label className="sr-only" htmlFor={`ov-${q.id}`}>{texts.rfi.change} — {q.text}</label>
        <select id={`ov-${q.id}`} value={selectValue}
          onChange={(e) => onOverride(e.target.value === AUTO ? undefined : e.target.value === SKIP ? null : e.target.value)}
          className="w-full rounded-xl border-2 border-fg bg-card px-2.5 py-1.5 text-sm font-semibold focus:shadow-[3px_3px_0_0_var(--color-magic-500)] focus:outline-none">
          <option value={AUTO}>{q.fact_label && override === undefined ? `Auto : ${q.fact_label}` : 'Auto'}</option>
          <option value={SKIP}>{texts.rfi.ignore}</option>
          {q.alternatives.length > 0 && (
            <optgroup label="Suggestions">
              {q.alternatives.map((a) => <option key={`alt-${a.fact}`} value={a.fact}>{a.label} ({Math.round(a.confidence * 100)}%)</option>)}
            </optgroup>
          )}
          {(['fund', 'share'] as const).map((scope) => (
            <optgroup key={scope} label={scope === 'fund' ? 'Fonds' : 'Part'}>
              {facts.filter((f) => f.scope === scope).map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
            </optgroup>
          ))}
        </select>
        {q.fact && <div className="mt-1.5"><ConfidenceBar value={q.confidence} /></div>}
      </td>
      <td className="py-3">
        <span className={`inline-block whitespace-nowrap rounded-full border-2 border-fg px-2.5 py-0.5 text-xs font-bold ${STATUS_STYLE[q.status]}`}>
          {texts.rfi.status[q.status]}
        </span>
      </td>
    </tr>
  )
}

export default function Rfi() {
  const toast = useToast()
  const root = useRef<HTMLDivElement>(null)
  const recent = useAsync(() => api.rfi.documents(), [])
  const factsQuery = useAsync(() => api.rfi.facts(), [])
  const [doc, setDoc] = useState<RfiDocument | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [pid, setPid] = useState<string | null>(null)
  const [isin, setIsin] = useState<string | null>(null)
  const [asOf, setAsOf] = useState(todayIso())
  const [language, setLanguage] = useState<'fr' | 'en'>('fr')
  const [overrides, setOverrides] = useState<Record<string, string | null>>({})
  const [overwrite, setOverwrite] = useState(false)
  const [analysis, setAnalysis] = useState<RfiAnalysis | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [result, setResult] = useState<RfiGenerated | null>(null)
  const [filter, setFilter] = useState<Filter>('todo')

  useGSAP(() => {
    if (prefersReducedMotion()) return
    gsap.from('[data-enter]', { y: 30, opacity: 0, stagger: 0.08, duration: d('slow'), ease: ease.out })
  }, { scope: root, dependencies: [doc?.id, !!result] })

  const request = (extra: Partial<RfiRequest> = {}): RfiRequest => ({ pid, isin, as_of: asOf, language, overrides, overwrite, ...extra })

  const open = async (loader: Promise<RfiDocument>) => {
    setBusy(true)
    setError(null)
    setAnalysis(null)
    setResult(null)
    setOverrides({})
    try {
      const d = await loader
      setDoc(d)
      setLanguage(d.language ?? 'fr')
      const first = d.suggestions?.[0]
      setPid(first?.pid ?? null)
      setIsin(first?.isin ?? null)
      recent.reload()
      if (first) void analyze(d, { pid: first.pid, isin: first.isin, language: d.language ?? 'fr', overrides: {} })
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(String(e)))
    } finally {
      setBusy(false)
    }
  }

  const analyze = async (target: RfiDocument | null = doc, extra: Partial<RfiRequest> = {}) => {
    if (!target) return
    setAnalyzing(true)
    setResult(null)
    try {
      setAnalysis(await api.rfi.answers(target.id, request(extra)))
    } catch (e) {
      toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
    } finally {
      setAnalyzing(false)
    }
  }

  const setOverride = (id: string, value: string | null | undefined) => {
    const next = { ...overrides }
    if (value === undefined) delete next[id]
    else next[id] = value
    setOverrides(next)
    void analyze(doc, { overrides: next })
  }

  const generate = async () => {
    if (!doc) return
    setGenerating(true)
    try {
      const r = await api.rfi.generate(doc.id, request())
      setResult(r)
      window.dispatchEvent(new Event('rfp:shower'))
      toast('success', texts.rfi.done(r.written))
    } catch (e) {
      toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
    } finally {
      setGenerating(false)
    }
  }

  const reset = () => {
    setDoc(null)
    setAnalysis(null)
    setResult(null)
    setOverrides({})
  }

  const facts = factsQuery.data ?? []
  const visible = useMemo(() => (analysis?.questions ?? []).filter((q) =>
    filter === 'all' ? true : filter === 'unmatched' ? q.status === 'unmatched' || q.status === 'no_value' : q.status === 'fill' || q.status === 'existing' || q.status === 'skipped'),
  [analysis, filter])
  const toWrite = analysis ? analysis.stats.fill + (overwrite ? analysis.stats.existing : 0) : 0

  return (
    <div ref={root} className="mx-auto w-[min(100%-2rem,82rem)] pt-10 sm:pt-14">
      <header data-enter className="max-w-3xl">
        <p className="eyebrow"><FileQuestion size={13} aria-hidden="true" />{texts.rfi.eyebrow}</p>
        <h1 className="mt-4 text-[clamp(2.4rem,6vw,4.5rem)] font-bold">{texts.rfi.title}</h1>
        <p className="mt-4 text-lg font-semibold text-fg-2">{texts.rfi.lead}</p>
      </header>

      {!doc && (
        <div className="mt-10 grid gap-8 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          <div data-enter className="flex flex-col gap-4">
            <Dropzone onFile={(f) => open(api.rfi.upload(f))} busy={busy} accept={ACCEPT}
              title={texts.rfi.drop} body={texts.rfi.dropHint} activeTitle={texts.rfi.dropActive} busyTitle={texts.rfi.reading} />
            <div className="flex flex-wrap gap-3">
              <Button onClick={() => open(api.rfi.demo('xlsx'))} disabled={busy} icon={<FileSpreadsheet size={18} />}>{texts.rfi.demoXlsx}</Button>
              <Button onClick={() => open(api.rfi.demo('docx'))} disabled={busy} icon={<FileText size={18} />}>{texts.rfi.demoDocx}</Button>
            </div>
            {error && <ErrorState error={error} />}
          </div>
          <aside data-enter className="glass rounded-[var(--radius-card)] p-6">
            <h2 className="text-2xl">{texts.rfi.recent}</h2>
            {recent.loading && !recent.data && <Loading compact />}
            {recent.data && recent.data.length === 0 && <p className="mt-3 text-fg-2">{texts.rfi.noRecent}</p>}
            <ul className="mt-4 flex flex-col gap-2">
              {recent.data?.slice(0, 8).map((r) => (
                <li key={r.id}>
                  <button onClick={() => open(api.rfi.document(r.id))} disabled={busy}
                    className="flex w-full items-center gap-3 rounded-xl border-2 border-fg bg-card px-3 py-2 text-left transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow-[3px_3px_0_0_var(--color-fg)]">
                    {r.suffix === '.docx' ? <FileText size={18} aria-hidden="true" className="text-magic-300" /> : <FileSpreadsheet size={18} aria-hidden="true" className="text-mint-300" />}
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-semibold">{r.filename}</span>
                      <span className="text-xs font-semibold text-fg-3">{r.user} · {formatRelative(r.uploaded_at)}</span>
                    </span>
                    <ArrowRight size={16} aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          </aside>
        </div>
      )}

      {doc && (
        <>
          <section data-enter className="glass mt-10 rounded-[var(--radius-card)] p-6 sm:p-8">
            <div className="flex flex-wrap items-center gap-3">
              <span className="grid size-12 place-items-center rounded-2xl border-[2.5px] border-fg bg-sun-400">
                {doc.kind === 'docx' ? <FileText size={24} aria-hidden="true" /> : <FileSpreadsheet size={24} aria-hidden="true" />}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate font-display text-xl font-semibold">{doc.filename}</p>
                <p className="text-sm font-semibold text-fg-2">
                  {texts.rfi.questions(doc.question_count ?? 0)} · {doc.language === 'en' ? 'anglais' : 'français'} {texts.rfi.detected}
                </p>
              </div>
              <a href={api.rfi.originalUrl(doc.id)} className="text-sm font-bold text-magic-300 underline decoration-2 underline-offset-4">{texts.rfi.original}</a>
              <Button variant="ghost" size="sm" onClick={reset} icon={<RotateCcw size={16} />}>{texts.rfi.restart}</Button>
            </div>

            <h2 className="mt-8 text-2xl">{texts.rfi.step1}</h2>
            <div className="mt-4 grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
              <FundPicker doc={doc} pid={pid} isin={isin} onPick={(p, i) => { setPid(p); setIsin(i) }} />
              <div className="flex flex-col gap-4">
                <Field label={texts.rfi.asOf}>
                  {({ id }) => <TextInput id={id} type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />}
                </Field>
                <Field label={texts.rfi.language}>
                  {({ id }) => (
                    <Select id={id} value={language} onChange={(e) => setLanguage(e.target.value as 'fr' | 'en')}>
                      <option value="fr">Français</option>
                      <option value="en">English</option>
                    </Select>
                  )}
                </Field>
                <Button variant="primary" onClick={() => analyze()} loading={analyzing} disabled={!pid} icon={<Wand2 size={18} />}>
                  {analyzing ? texts.rfi.analyzing : texts.rfi.analyze}
                </Button>
                {!pid && <p className="text-sm font-semibold text-fg-3">{texts.rfi.pickFund}</p>}
              </div>
            </div>
          </section>

          {analysis && (
            <section data-enter className="glass mt-8 rounded-[var(--radius-card)] p-6 sm:p-8" aria-busy={analyzing}>
              <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                  <h2 className="text-2xl">{texts.rfi.step2}</h2>
                  <p className="mt-1 flex flex-wrap gap-2 text-sm font-bold">
                    {(Object.keys(analysis.stats) as RfiStatus[]).filter((k) => analysis.stats[k] > 0).map((k) => (
                      <span key={k} className={`rounded-full border-2 border-fg px-2.5 py-0.5 ${STATUS_STYLE[k]}`}>{analysis.stats[k]} {texts.rfi.status[k]}</span>
                    ))}
                  </p>
                </div>
                <div role="group" aria-label="Filtrer les questions" className="flex gap-2">
                  {(['todo', 'all', 'unmatched'] as Filter[]).map((f) => (
                    <button key={f} onClick={() => setFilter(f)} aria-pressed={filter === f}
                      className={`rounded-full border-2 px-3.5 py-1.5 text-sm font-bold transition-colors ${filter === f ? 'border-fg bg-magic-500 text-white' : 'border-fg/30 hover:border-fg'}`}>
                      {texts.rfi.filters[f]}
                    </button>
                  ))}
                </div>
              </div>
              {analysis.errors.length > 0 && (
                <ul className="mt-4 rounded-xl border-2 border-warning bg-sun-400/20 p-3 text-sm font-semibold text-warning">
                  {analysis.errors.map((e) => <li key={e}>{e}</li>)}
                </ul>
              )}
              {filter === 'unmatched' && <p className="mt-4 text-sm font-semibold text-fg-2">{texts.rfi.unmatchedHint}</p>}
              <div className={`mt-4 overflow-x-auto transition-opacity ${analyzing ? 'opacity-60' : ''}`}>
                {visible.length === 0 ? (
                  <EmptyState title="Rien dans ce filtre." body="Essayez « Toutes »." />
                ) : (
                  <table className="w-full min-w-[46rem] text-left">
                    <thead>
                      <tr className="text-xs font-bold uppercase tracking-wider text-fg-3">
                        <th className="pb-2 pr-4">{texts.rfi.columns.question}</th>
                        <th className="pb-2 pr-4">{texts.rfi.columns.answer}</th>
                        <th className="pb-2 pr-4">{texts.rfi.columns.source}</th>
                        <th className="pb-2"><span className="sr-only">Statut</span></th>
                      </tr>
                    </thead>
                    <tbody>
                      {visible.map((q) => (
                        <QuestionRow key={q.id} q={q} facts={facts} override={q.id in overrides ? overrides[q.id] : undefined} onOverride={(v) => setOverride(q.id, v)} />
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
              <p className="mt-4 text-xs font-semibold text-fg-3">{texts.rfi.legal}</p>
            </section>
          )}

          {analysis && (
            <section data-enter className="mt-8 rounded-[var(--radius-card)] border-[2.5px] border-fg bg-sun-400 p-6 shadow-[var(--shadow-pop-lg)] sm:p-8">
              <h2 className="text-2xl">{texts.rfi.step3}</h2>
              {!result ? (
                <div className="mt-4 flex flex-wrap items-center justify-between gap-4">
                  <Switch checked={overwrite} onChange={(v) => { setOverwrite(v); void analyze(doc, { overwrite: v }) }} label={texts.rfi.overwrite} />
                  <Button size="lg" onClick={generate} loading={generating} disabled={toWrite === 0} icon={<Sparkles size={20} />} className="!bg-card">
                    {generating ? texts.rfi.generating : `${texts.rfi.generate} (${toWrite})`}
                  </Button>
                </div>
              ) : (
                <div className="mt-4 flex flex-wrap items-center gap-4">
                  <span className="grid size-14 place-items-center rounded-full border-[2.5px] border-fg bg-mint-400"><Check size={28} aria-hidden="true" /></span>
                  <div className="flex-1">
                    <p className="font-display text-2xl font-semibold">{texts.rfi.done(result.written)}</p>
                    <p className="font-semibold text-fg-2">{result.file} · {texts.rfi.minutes(result.written * 2)}</p>
                  </div>
                  <a href={result.download} className="inline-flex h-14 items-center gap-2 rounded-full border-[2.5px] border-fg bg-card px-7 font-display text-lg font-semibold shadow-[3px_3px_0_0_var(--color-fg)] transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow-[5px_5px_0_0_var(--color-fg)]">
                    <Download size={20} aria-hidden="true" />{texts.rfi.download}
                  </a>
                  <Button variant="ghost" onClick={reset} icon={<RotateCcw size={16} />}>{texts.rfi.restart}</Button>
                </div>
              )}
            </section>
          )}
        </>
      )}
    </div>
  )
}
