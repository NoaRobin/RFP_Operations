/**
 * Recherche par le sens dans la bibliothèque Qvidian.
 * Résultats instantanés pendant la frappe (mots + sens), puis affinés par le reranker quand la question est posée.
 * Facettes : niveau (société / stratégie / fonds / part), thème, fonds, dossier, langue ; tri par pertinence ou usage.
 * Clavier : ↑ ↓ pour naviguer, Entrée pour ouvrir, Espace pour cocher, C pour copier le texte.
 */
import { Suspense, lazy, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { AlertTriangle, Check, ChevronDown, ChevronRight, Copy, Languages, Search, Sparkles, Wand2, X } from 'lucide-react'
import { Highlight, LevelBadge, ScoreRing, ago, copyText } from '../../../components/qvidian/Bits'
import { Select, Switch } from '../../../components/ui/Field'
import { useToast } from '../../../components/ui/Toast'
import { LiquidGauge } from '../../../components/qviapi/LiquidGauge'
import { useReducedMotion } from '../../../motion/useReducedMotion'
import { texts } from '../../../content/texts'
import { api, ApiError } from '../../../lib/api'
import type { QvidianFacet, QvidianFilters, QvidianHit, QvidianSearchResult, QvidianSuggest } from '../../../lib/types'
import { useQvidian } from '../context'

const KeyboardScene = lazy(() => import('../../../components/qviapi/KeyboardScene'))
const webgl = () => { try { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')) } catch { return false } }
const Q = texts.qvidian
type FacetKey = 'scope' | 'theme' | 'fund'

function Facet({ title, values, active, onToggle }: { title: string; values: QvidianFacet[]; active: string[]; onToggle: (v: string) => void }) {
  if (!values.length) return null
  return (
    <fieldset className="flex min-w-0 flex-col gap-1">
      <legend className="mb-1 text-[0.7rem] font-bold uppercase tracking-widest text-fg-3">{title}</legend>
      {values.slice(0, 10).map((v) => {
        const on = active.includes(v.value)
        return (
          <label key={v.value} className={`flex min-w-0 cursor-pointer items-start gap-2 rounded-lg px-2 py-1 text-sm font-semibold ${on ? 'bg-sun-400/50' : 'hover:bg-card-2'}`}>
            <input type="checkbox" checked={on} onChange={() => onToggle(v.value)} className="mt-0.5 size-4 shrink-0 accent-[var(--color-magic-500)]" />
            <span className="min-w-0 flex-1 break-words leading-snug [overflow-wrap:anywhere]">{v.label ?? v.value}</span>
            <span className="mt-0.5 shrink-0 text-xs tabular-nums text-fg-3">{v.count}</span>
          </label>
        )
      })}
    </fieldset>
  )
}

function Hit({ hit, active, selected, onSelect, onCopy, query }: {
  hit: QvidianHit; active: boolean; selected: boolean; onSelect: () => void; onCopy: () => void; query: string
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLElement>(null)
  useEffect(() => { if (active) ref.current?.scrollIntoView({ block: 'nearest' }) }, [active])
  const signals = hit.signals
  return (
    <article ref={ref} aria-current={active || undefined}
      className={`rounded-[var(--radius-card)] border-[2.5px] bg-card p-4 transition-shadow ${active ? 'border-fg shadow-[5px_5px_0_0_var(--color-magic-500)]' : 'border-fg/70'} ${selected ? 'ring-4 ring-sun-400/70' : ''}`}>
      <div className="flex gap-4">
        {hit.score !== null && <ScoreRing score={hit.score} />}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start gap-2">
            <Link to={`/qvidian/contenu/${hit.id}`} state={{ from: query }} className="min-w-0 flex-1 font-display text-lg font-semibold leading-snug hover:underline">
              {hit.title || `#${hit.id}`}
            </Link>
            <span className="text-xs font-bold text-fg-3">#{hit.id}</span>
          </div>
          <p className="mt-0.5 truncate text-xs font-semibold text-fg-3">{hit.folder_path || '—'}</p>
          <div className="mt-2"><LevelBadge level={hit.level} /></div>
          <p className="mt-2 text-sm font-medium leading-relaxed text-fg-2"><Highlight text={hit.snippet} spans={hit.highlights} /></p>
          {hit.history && (
            <p className="mt-2 rounded-xl border-l-4 border-sun-400 bg-sun-400/15 px-3 py-1.5 text-xs font-semibold">
              <b>{Q.historyChosen(hit.history.files)}</b> · « {hit.history.questions.slice(0, 2).join(' » · « ')} »
              {hit.history.examples[0] ? <span className="text-fg-3"> · {hit.history.examples[0].file}, {hit.history.examples[0].date}</span> : null}
            </p>
          )}
          {hit.why.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Pourquoi ce résultat">
              {hit.why.slice(0, 5).map((w) => (
                <li key={w} className={`rounded-full px-2 py-0.5 text-[0.7rem] font-bold ${/autre fonds|expiré|désactivé|corriger/.test(w) ? 'bg-bubble-400/30' : 'bg-mint-400/30'}`}>{w}</li>
              ))}
            </ul>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs font-semibold text-fg-2">
            <span className="tabular-nums">{Q.uses(hit.times_used)}</span>
            <span>{Q.lastUsed} {ago(hit.last_used)}</span>
            <span className="inline-flex items-center gap-1"><Languages size={12} aria-hidden="true" />{Q.langLabel[hit.language] ?? hit.language}</span>
            {hit.expired && <span className="rounded-full bg-bubble-400/30 px-2 font-bold">expiré</span>}
            {!hit.enabled && <span className="rounded-full bg-card-3 px-2 font-bold">désactivé</span>}
            {hit.issues.length > 0 && <span className="inline-flex items-center gap-1 font-bold text-warning"><AlertTriangle size={12} aria-hidden="true" />{hit.issues.length} défaut{hit.issues.length > 1 ? 's' : ''}</span>}
            {signals && (
              <span className="hidden gap-2 text-fg-3 md:inline-flex" title={Q.signals}>
                · {Q.signalCoverage} {Math.round(signals.coverage * 100)} %
                {signals.semantic !== null && <> · {Q.signalSemantic} {signals.semantic.toFixed(2)}</>}
                {signals.rerank !== null && <> · {Q.signalRerank} {Math.round(signals.rerank * 100)} %</>}
              </span>
            )}
            <span className="ml-auto flex gap-1.5">
              <button onClick={onCopy} className="inline-flex items-center gap-1 rounded-full border-2 border-fg/40 px-2.5 py-1 font-bold hover:border-fg"><Copy size={12} aria-hidden="true" />{Q.copy}</button>
              <button onClick={onSelect} aria-pressed={selected} className={`inline-flex items-center gap-1 rounded-full border-2 px-2.5 py-1 font-bold ${selected ? 'border-fg bg-sun-400' : 'border-fg/40 hover:border-fg'}`}>
                <Check size={12} aria-hidden="true" />{selected ? Q.selectedOne : Q.select}
              </button>
            </span>
          </div>
          {hit.variants.length > 0 && (
            <div className="mt-2">
              <button onClick={() => setOpen(!open)} className="inline-flex items-center gap-1 text-xs font-bold text-magic-300 hover:underline" aria-expanded={open}>
                {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}{Q.variants(hit.variants.length)}
              </button>
              {open && (
                <ul className="mt-1 flex flex-col gap-1 border-l-2 border-fg/20 pl-3">
                  {hit.variants.map((v) => (
                    <li key={v.id} className="text-xs font-semibold">
                      <Link to={`/qvidian/contenu/${v.id}`} className="hover:underline">#{v.id} · {v.title}</Link>
                      <span className="text-fg-3"> · {Q.uses(v.times_used)} · {ago(v.last_used)}{v.expired ? ' · expiré' : ''}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      </div>
    </article>
  )
}

export function SearchView() {
  const toast = useToast()
  const navigate = useNavigate()
  const { selected, toggle, fail } = useQvidian()
  const [params, setParams] = useSearchParams()
  const [q, setQ] = useState(params.get('q') ?? '')
  const location = useLocation()
  const fromScope = (location.state as { scope?: string } | null)?.scope
  const [filters, setFilters] = useState<QvidianFilters>({ include_expired: true, ...(fromScope ? { scope: [fromScope] } : {}) })
  const [sort, setSort] = useState('pertinence')
  const [res, setRes] = useState<QvidianSearchResult | null>(null)
  const [busy, setBusy] = useState(false)
  const pressed = useRef('')
  const [best, setBest] = useState<QvidianSuggest['choices'][number] | null>(null)
  useEffect(() => {
    const text = (params.get('q') ?? '').trim()
    if (text.length < 8) { setBest(null); return }
    let alive = true
    api.qvidian.suggest(text).then((r) => alive && setBest(r.choices[0] ?? null)).catch(() => alive && setBest(null))
    return () => { alive = false }
  }, [params])
  const reduced = useReducedMotion()
  const show3d = !reduced && webgl()
  const [refining, setRefining] = useState(false)
  const [active, setActive] = useState(0)
  const seq = useRef(0)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => { input.current?.focus() }, [])
  useEffect(() => {
    const fromUrl = params.get('q') ?? ''
    if (fromUrl !== q) setQ(fromUrl)
  }, [params]) // eslint-disable-line react-hooks/exhaustive-deps

  // Frappe : résultats rapides (mots + sens) ; à l'arrêt : affinage par le reranker
  useEffect(() => {
    const n = ++seq.current
    setBusy(true)
    const quick = window.setTimeout(async () => {
      try {
        const r = await api.qvidian.search(q, filters, sort, false)
        if (n !== seq.current) return
        setRes(r); setActive(0); setBusy(false)
        if (q.trim() && r.engine.reranker && sort === 'pertinence') {
          setRefining(true)
          const fine = await api.qvidian.search(q, filters, sort, true)
          if (n === seq.current) setRes(fine)
        }
      } catch (e) {
        if (n === seq.current) { setBusy(false); fail(e instanceof ApiError ? e : new ApiError(String(e))) }
      } finally {
        if (n === seq.current) setRefining(false)
      }
    }, q.trim() ? 220 : 0)
    return () => window.clearTimeout(quick)
  }, [q, filters, sort, fail])

  const commit = (value: string) => {
    const next = new URLSearchParams(params)
    if (value.trim()) next.set('q', value)
    else next.delete('q')
    setParams(next, { replace: true })
  }
  const toggleFacet = (key: FacetKey, value: string) => setFilters((f) => {
    const cur = f[key] ?? []
    return { ...f, [key]: cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value] }
  })
  const results = res?.results ?? []
  const copy = async (hit: QvidianHit) => {
    const ok = await copyText(hit.text)
    toast(ok ? 'success' : 'error', ok ? Q.copied : Q.copyFailed)
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      const typing = t.closest('input, textarea, select, [contenteditable="true"]')
      if (!results.length) return
      if (e.key === 'ArrowDown' && (!typing || t === input.current)) { e.preventDefault(); setActive((i) => Math.min(i + 1, results.length - 1)) }
      else if (e.key === 'ArrowUp' && !typing) { e.preventDefault(); setActive((i) => Math.max(i - 1, 0)) }
      else if (e.key === 'Enter' && !typing) navigate(`/qvidian/contenu/${results[active].id}`)
      else if (e.key === ' ' && !typing) { e.preventDefault(); toggle(results[active].id) }
      else if (e.key.toLowerCase() === 'c' && !typing && !e.metaKey && !e.ctrlKey) void copy(results[active])
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  // Jauges des moteurs : part des 10 premiers résultats que chaque moteur a fait remonter (dans son top 20)
  const gauges = useMemo(() => {
    const top = results.slice(0, 10)
    const share = (f: (h: QvidianHit) => boolean) => (top.length ? top.filter(f).length / top.length : 0)
    const rank = (k: string) => (h: QvidianHit) => (h.signals?.ranks?.[k] ?? 99) < 20
    const E = texts.qviapi.engine
    return [
      { key: 'bm25', label: E.bm25, color: '#0969da', level: share(rank('bm25')) },
      { key: 'ngram', label: E.ngram, color: '#6e7781', level: share(rank('ngram')) },
      { key: 'dense', label: E.dense, color: '#54aeff', level: share(rank('dense')), off: !!res && !res.engine.encoder },
      { key: 'rerank', label: E.rerank, color: '#8250df', level: share((h) => (h.signals?.rerank ?? 0) >= 0.5), off: !!res && !res.engine.reranker },
      { key: 'history', label: E.history, color: '#1a7f37', level: share(rank('history')) },
    ]
  }, [results, res])
  const filterCount = useMemo(() => (filters.scope?.length ?? 0) + (filters.theme?.length ?? 0) + (filters.fund?.length ?? 0)
    + (filters.language ? 1 : 0) + (filters.folder ? 1 : 0) + (filters.min_uses ? 1 : 0) + (filters.only_issues ? 1 : 0) + (filters.include_disabled ? 1 : 0)
    + (filters.include_expired === false ? 1 : 0), [filters])

  return (
    <div className="flex flex-col gap-5">
      <header data-enter>
        <h1 className="text-2xl font-semibold">{Q.searchTitle}</h1>
        <p className="mt-2 max-w-3xl text-sm font-semibold text-fg-2">{Q.searchLead}</p>
      </header>
      <section data-enter aria-label={texts.qviapi.engines} className="grid items-end gap-4 md:grid-cols-[auto_minmax(0,1fr)_auto]">
        <div className="hidden gap-3 md:flex">{gauges.slice(0, 2).map((g) => <LiquidGauge key={g.key} label={g.label} color={g.color} level={g.level} off={g.off} busy={busy || (refining && g.key === 'rerank')} />)}</div>
        <div className="flex min-w-0 flex-col">
          {show3d && <Suspense fallback={<div className="h-36" />}><KeyboardScene pressed={pressed} busy={busy || refining} /></Suspense>}
          <form role="search" onSubmit={(e) => { e.preventDefault(); commit(q) }}
            className="relative rounded-[var(--radius-card)] border border-line bg-field">
            <Search size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-fg-3" aria-hidden="true" />
            <input ref={input} value={q} onChange={(e) => setQ(e.target.value)} onBlur={() => commit(q)} placeholder={Q.searchPlaceholder} aria-label={Q.searchTitle}
              onKeyDown={(e) => { pressed.current = e.key === ' ' ? ' ' : e.key.length === 1 ? e.key.toUpperCase() : '' }}
              className="h-12 w-full rounded-[var(--radius-card)] bg-transparent pl-11 pr-28 text-base placeholder:font-normal placeholder:text-fg-3 focus:outline-none" />
            <span className="absolute right-4 top-1/2 flex -translate-y-1/2 items-center gap-2 text-xs font-bold text-fg-3" aria-live="polite">
              {busy ? '…' : refining ? <><Wand2 size={14} className="animate-pulse" aria-hidden="true" />{Q.refining}</> : res?.timings.total_ms ? Q.timings(res.timings.total_ms) : ''}
              {q && <button type="button" onClick={() => { setQ(''); commit('') }} aria-label="Effacer" className="rounded-full p-1 hover:bg-card-2"><X size={16} /></button>}
            </span>
          </form>
        </div>
        <div className="hidden gap-3 md:flex">{gauges.slice(2).map((g) => <LiquidGauge key={g.key} label={g.label} color={g.color} level={g.level} off={g.off} busy={busy || (refining && g.key === 'rerank')} />)}</div>
        <div className="flex flex-wrap justify-center gap-3 md:hidden">{gauges.map((g) => <LiquidGauge key={g.key} label={g.label} color={g.color} level={g.level} off={g.off} busy={busy} />)}</div>
      </section>

      {res && res.query && (
        <div data-enter className="flex flex-wrap items-center gap-2 text-xs font-bold">
          <span className="inline-flex items-center gap-1 text-fg-3"><Sparkles size={13} aria-hidden="true" />{Q.understood} :</span>
          {res.language && <span className="rounded-full bg-card-2 px-2 py-0.5">{Q.langLabel[res.language] ?? res.language}</span>}
          {res.pivot && <span className="rounded-full bg-card-2 px-2 py-0.5">{Q.pivot} « {res.pivot} »</span>}
          {res.level.scope !== 'generique' && <span className="rounded-full bg-magic-400/30 px-2 py-0.5">{Q.targetScope} : {res.level.scope_label}</span>}
          {res.level.funds.map((f) => <span key={f} className="rounded-full bg-mint-400/40 px-2 py-0.5">{Q.targetFund} : {f}</span>)}
          {res.expansions.slice(0, 4).map((x) => <span key={x} className="rounded-full border border-fg/30 px-2 py-0.5 font-semibold">{Q.expansions} : {x}</span>)}
          <span className="ml-auto font-semibold text-fg-3">
            {res.engine.encoder ? Q.engineNeural(res.engine.encoder, res.engine.reranker) : Q.engineLexical}
            {res.timings.rerank_ms ? ` · ${Q.refined}` : ''}
          </span>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-[15rem_minmax(0,1fr)]">
        <aside data-enter className="flex h-fit min-w-0 flex-col gap-4 rounded-[var(--radius-card)] border-2 border-fg bg-card p-4 lg:sticky lg:top-24" aria-label="Filtres">
          <label className="flex flex-col gap-1 text-xs font-bold text-fg-3">{Q.sort}
            <Select value={sort} onChange={(e) => setSort(e.target.value)}>
              {Object.entries(Q.sorts).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
          </label>
          <Facet title={Q.facetScope} values={res?.facets.scope ?? []} active={filters.scope ?? []} onToggle={(v) => toggleFacet('scope', v)} />
          <Facet title={Q.facetFund} values={res?.facets.fund ?? []} active={filters.fund ?? []} onToggle={(v) => toggleFacet('fund', v)} />
          <Facet title={Q.facetTheme} values={res?.facets.theme ?? []} active={filters.theme ?? []} onToggle={(v) => toggleFacet('theme', v)} />
          {(res?.facets.language.length ?? 0) > 1 && (
            <label className="flex flex-col gap-1 text-xs font-bold text-fg-3">{Q.facetLanguage}
              <Select value={filters.language ?? ''} onChange={(e) => setFilters((f) => ({ ...f, language: e.target.value || undefined }))}>
                <option value="">—</option>
                {res!.facets.language.map((l) => <option key={l.value} value={l.value}>{Q.langLabel[l.value] ?? l.value} ({l.count})</option>)}
              </Select>
            </label>
          )}
          <label className="flex flex-col gap-1 text-xs font-bold text-fg-3">{Q.minUses}
            <Select value={filters.min_uses ?? 0} onChange={(e) => setFilters((f) => ({ ...f, min_uses: Number(e.target.value) || undefined }))}>
              {[0, 1, 5, 10, 25, 50].map((n) => <option key={n} value={n}>{n ? `${n} fois` : '—'}</option>)}
            </Select>
          </label>
          <Switch checked={filters.include_expired !== false} onChange={(v) => setFilters((f) => ({ ...f, include_expired: v }))} label={Q.includeExpired} />
          <Switch checked={!!filters.include_disabled} onChange={(v) => setFilters((f) => ({ ...f, include_disabled: v }))} label={Q.includeDisabled} />
          <Switch checked={!!filters.only_issues} onChange={(v) => setFilters((f) => ({ ...f, only_issues: v }))} label={Q.onlyIssuesFacet} />
          {filterCount > 0 && <button onClick={() => setFilters({ include_expired: true })} className="text-left text-xs font-bold underline">{Q.clearFilters} ({filterCount})</button>}
        </aside>

        <section aria-live="polite" aria-busy={busy} className="flex min-w-0 flex-col gap-3">
          <p className="flex flex-wrap items-center gap-2 text-sm font-bold text-fg-2">
            {res ? Q.results(res.total) : ''}
            {res?.index?.running && <span className="rounded-full bg-sun-400/50 px-2 py-0.5 text-xs">{Q.indexing} {res.index.done}/{res.index.total}</span>}
            <span className="ml-auto hidden text-xs font-semibold text-fg-3 md:inline">{Q.keyboard}</span>
          </p>
          {best && (
            <article className="rounded-[var(--radius-card)] border-2 border-magic-500 bg-card p-4" aria-label={texts.qviapi.recommended}>
              <p className="flex flex-wrap items-center gap-2 text-xs font-bold text-magic-300">
                <Wand2 size={14} aria-hidden="true" />{texts.qviapi.recommended}
                <span className="font-semibold text-fg-3">{texts.qviapi.recommendedWhy(Math.round(best.share * 100))}</span>
                <button onClick={async () => { const ok = await copyText(best.value); toast(ok ? 'success' : 'error', ok ? Q.copied : Q.copyFailed) }}
                  className="ml-auto inline-flex items-center gap-1 rounded-full border border-fg/30 px-2.5 py-1 text-fg hover:border-fg"><Copy size={13} aria-hidden="true" />{Q.copy}</button>
              </p>
              <p className="mt-2 line-clamp-6 whitespace-pre-line text-sm">{best.value}</p>
              <p className="mt-1 text-xs text-fg-3">{best.why} · {best.contents.map((x) => <Link key={x} to={`/qvidian/contenu/${x}`} className="mr-1 underline">#{x}</Link>)}</p>
            </article>
          )}
          {res && results.length === 0 && !busy && <p className="rounded-2xl border-2 border-dashed border-fg/40 p-6 text-center font-semibold text-fg-2">{Q.noResults}</p>}
          {results.map((hit, i) => (
            <Hit key={hit.id} hit={hit} active={i === active} selected={selected.has(hit.id)} query={q}
              onSelect={() => toggle(hit.id)} onCopy={() => void copy(hit)} />
          ))}
        </section>
      </div>
    </div>
  )
}
