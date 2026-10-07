import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CalendarClock, Download, Eye, FileSpreadsheet, FlaskConical, Play, Save, ShieldCheck, Sparkles, Trash2, X } from 'lucide-react'
import { Dropzone } from '../components/atelier/Dropzone'
import { ExtractionPanel } from '../components/atelier/ExtractionPanel'
import { SheetGrid } from '../components/atelier/SheetGrid'
import { ScheduleDialog } from '../components/ScheduleDialog'
import { Button, buttonClass } from '../components/ui/Button'
import { Dialog } from '../components/ui/Dialog'
import { Field, Select, Switch, TextInput } from '../components/ui/Field'
import { EmptyState, ErrorState, Loading } from '../components/ui/States'
import { Badge } from '../components/ui/StatusPill'
import { useToast } from '../components/ui/Toast'
import { texts } from '../content/texts'
import { api, ApiError } from '../lib/api'
import { formatBytes, formatRelative, todayIso } from '../lib/format'
import { useAsync } from '../lib/hooks'
import type { Extraction, Mapping, Preview, Recipe, WorkbookAnalysis } from '../lib/types'
import { gsap, useGSAP } from '../motion/gsap'
import { d, dist, ease, stagger } from '../motion/tokens'

/* ======================================================================= accueil de l'atelier */
function AtelierHome({ onOpen, onRecipe }: { onOpen: (a: WorkbookAnalysis) => void; onRecipe: (r: Recipe) => void }) {
  const navigate = useNavigate()
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const workbooks = useAsync(() => api.atelier.workbooks(), [])
  const recipes = useAsync(() => api.atelier.recipes(), [])
  const [scheduleFor, setScheduleFor] = useState<Recipe | null>(null)

  const load = async (promise: Promise<WorkbookAnalysis>) => {
    setBusy(true)
    setError(null)
    try {
      onOpen(await promise)
    } catch (e) {
      setError(e as ApiError)
    } finally {
      setBusy(false)
    }
  }

  const replay = async (recipe: Recipe) => {
    try {
      const run = await api.atelier.runRecipe(recipe.id!)
      navigate(`/executions/${run.id}`, { state: { run } })
    } catch (e) {
      toast('error', (e as ApiError).message, (e as ApiError).hint)
    }
  }

  return (
    <div className="grid gap-10 lg:grid-cols-[1.3fr_1fr]">
      <div className="flex flex-col gap-5" data-enter>
        <Dropzone busy={busy} onFile={(file) => load(api.atelier.upload(file))} />
        <div className="flex flex-wrap items-center gap-4">
          <Button variant="secondary" onClick={() => load(api.atelier.demo())} disabled={busy} icon={<FlaskConical size={16} />}>{texts.atelier.demo}</Button>
          <p className="flex items-center gap-2 text-sm text-haze"><ShieldCheck size={16} className="text-success" aria-hidden="true" />{texts.atelier.originalSafe}</p>
        </div>
        {error && <ErrorState error={error} />}
      </div>

      <div className="flex flex-col gap-6" data-enter>
        <section className="glass rounded-[var(--radius-card)] p-6">
          <h2 className="text-2xl">{texts.atelier.recipes}</h2>
          {recipes.data && recipes.data.length === 0 && <p className="mt-3 text-sm text-mist">{texts.atelier.noRecipes}</p>}
          <ul className="mt-4 flex flex-col gap-3">
            {recipes.data?.map((r) => (
              <li key={r.id} className="rounded-xl border border-line p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-medium text-ivory">{r.name}</p>
                    <p className="truncate text-xs text-haze">{r.workbook ?? '—'} · {r.mappings.length} correspondance(s) · {formatRelative(r.updated_at)}</p>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button size="sm" variant="primary" icon={<Play size={14} />} onClick={() => replay(r)} disabled={!r.workbook}>{texts.atelier.replay}</Button>
                  <Button size="sm" variant="secondary" onClick={() => onRecipe(r)} disabled={!r.workbook}>{texts.atelier.open}</Button>
                  <Button size="sm" variant="ghost" icon={<CalendarClock size={14} />} onClick={() => setScheduleFor(r)}>{texts.atelier.schedule}</Button>
                  <Button size="sm" variant="ghost" icon={<Trash2 size={14} />} aria-label={`${texts.atelier.delete} ${r.name}`}
                    onClick={async () => {
                      if (!window.confirm(texts.common.confirmDelete)) return
                      await api.atelier.deleteRecipe(r.id!)
                      recipes.reload()
                    }} />
                </div>
              </li>
            ))}
          </ul>
        </section>
        <section className="glass rounded-[var(--radius-card)] p-6">
          <h2 className="text-2xl">{texts.atelier.recentWorkbooks}</h2>
          {workbooks.data?.length === 0 && <p className="mt-3 text-sm text-mist">{texts.atelier.noWorkbooks}</p>}
          <ul className="mt-4 divide-y divide-[var(--color-line)]">
            {workbooks.data?.slice(0, 8).map((w) => (
              <li key={w.id} className="flex items-center gap-3 py-3">
                <FileSpreadsheet size={18} className="shrink-0 text-champagne-300" aria-hidden="true" />
                <button onClick={() => load(api.atelier.workbook(w.id))} className="min-w-0 flex-1 text-left">
                  <span className="block truncate text-sm text-ivory hover:text-champagne-200">{w.filename}</span>
                  <span className="text-xs text-haze">{w.uploaded_by} · {formatRelative(w.uploaded_at)} · {w.version_count} version(s)</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>
      {scheduleFor && (
        <ScheduleDialog open onClose={() => setScheduleFor(null)} targetType="recipe" targetId={scheduleFor.id!} label={scheduleFor.name} />
      )}
    </div>
  )
}

/* ======================================================================= établi */
function Workbench({ analysis: initial, recipe, extractions, onClose }: {
  analysis: WorkbookAnalysis
  recipe: Recipe | null
  extractions: Extraction[]
  onClose: () => void
}) {
  const navigate = useNavigate()
  const toast = useToast()
  const [analysis, setAnalysis] = useState(initial)
  const [sheetName, setSheetName] = useState(recipe?.sheet ?? initial.suggested_sheet ?? initial.sheets[0]?.name)
  const sheet = analysis.sheets.find((s) => s.name === sheetName) ?? analysis.sheets[0]
  const [headerRow, setHeaderRow] = useState(recipe?.header_row ?? sheet?.header_row ?? 1)
  const [keyColumn, setKeyColumn] = useState(recipe?.key_column ?? sheet?.key?.column ?? '')
  const [keyType, setKeyType] = useState(recipe?.key_type ?? sheet?.key?.key_type ?? 'isin_part')
  const [asOf, setAsOf] = useState(todayIso())
  const [overwrite, setOverwrite] = useState(recipe?.overwrite ?? false)
  const [highlight, setHighlight] = useState(recipe?.highlight_changes ?? false)
  const [mappings, setMappings] = useState<Mapping[]>(recipe?.mappings ?? [])
  const [selected, setSelected] = useState<string | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [showAfter, setShowAfter] = useState(true)
  const [busy, setBusy] = useState<'preview' | 'run' | 'save' | 'reload' | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [saveOpen, setSaveOpen] = useState(false)
  const [recipeName, setRecipeName] = useState(recipe?.name ?? analysis.filename.replace(/\.xls[xm]$/i, ''))
  const [savedRecipe, setSavedRecipe] = useState<Recipe | null>(recipe)
  const [scheduleOpen, setScheduleOpen] = useState(false)
  const statsRef = useRef<HTMLDivElement>(null)

  const byId = useMemo(() => Object.fromEntries(extractions.map((e) => [e.id, e])), [extractions])
  const proposals = useMemo(
    () => (sheet?.columns ?? []).filter((c) => c.proposed && byId[c.proposed]?.key === keyType && !mappings.some((m) => m.column === c.letter)),
    [sheet, byId, keyType, mappings],
  )

  // Changement de feuille : on repart des propositions de Merlin
  const firstSheet = useRef(true)
  useEffect(() => {
    if (!sheet) return
    if (firstSheet.current && recipe) {
      firstSheet.current = false
      return
    }
    firstSheet.current = false
    setHeaderRow(sheet.header_row)
    setKeyColumn(sheet.key?.column ?? '')
    setKeyType(sheet.key?.key_type ?? 'isin_part')
    setMappings(sheet.columns.filter((c) => c.proposed).map((c) => ({ column: c.letter, extraction: c.proposed! })))
    setSelected(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sheetName])

  useEffect(() => setPreview(null), [mappings, keyColumn, keyType, headerRow, asOf, overwrite, sheetName])

  const recipeBody = (): Recipe => ({
    id: savedRecipe?.id, name: recipeName, workbook_id: analysis.id, sheet: sheet.name, header_row: headerRow,
    key_column: keyColumn, key_type: keyType, as_of: asOf, overwrite, highlight_changes: highlight, mappings,
  })

  const assign = (column: string, extractionId: string) => {
    setMappings((all) => [...all.filter((m) => m.column !== column), { column, extraction: extractionId }])
    toast('info', `${byId[extractionId]?.label ?? extractionId} → colonne ${column}`)
  }

  const reanalyze = async (row: number) => {
    setHeaderRow(row)
    setBusy('reload')
    try {
      const next = await api.atelier.workbook(analysis.id, sheet.name, row)
      setAnalysis(next)
    } catch (e) {
      setError(e as ApiError)
    } finally {
      setBusy(null)
    }
  }

  const runPreview = async () => {
    setBusy('preview')
    setError(null)
    try {
      const result = await api.atelier.preview(recipeBody())
      setShowAfter(true)
      setPreview(result)
      requestAnimationFrame(() => {
        if (statsRef.current) gsap.from(statsRef.current.children, { opacity: 0, y: dist('lift'), stagger: stagger.base, duration: d('base'), ease: ease.out })
      })
    } catch (e) {
      setError(e as ApiError)
    } finally {
      setBusy(null)
    }
  }

  const execute = async () => {
    setBusy('run')
    setError(null)
    try {
      const run = await api.atelier.run(recipeBody())
      navigate(`/executions/${run.id}`, { state: { run } })
    } catch (e) {
      setError(e as ApiError)
      setBusy(null)
    }
  }

  const save = async (thenSchedule = false) => {
    setBusy('save')
    try {
      const saved = await api.atelier.saveRecipe(recipeBody())
      setSavedRecipe(saved)
      setSaveOpen(false)
      toast('success', texts.atelier.recipeSaved)
      if (thenSchedule) setScheduleOpen(true)
    } catch (e) {
      setError(e as ApiError)
    } finally {
      setBusy(null)
    }
  }

  if (!sheet) return <EmptyState title="Ce classeur ne contient aucune feuille visible." />

  return (
    <div className="flex flex-col gap-6">
      {/* Barre du classeur */}
      <div className="glass flex flex-wrap items-center gap-3 rounded-[var(--radius-card)] p-4" data-enter>
        <FileSpreadsheet className="text-champagne-300" size={22} aria-hidden="true" />
        <div className="min-w-0">
          <p className="truncate font-medium">{analysis.filename}</p>
          <p className="text-xs text-haze">{formatBytes(analysis.size)} · {texts.atelier.targets(sheet.target_count)}</p>
        </div>
        <div role="tablist" aria-label={texts.atelier.sheet} className="ml-auto flex flex-wrap gap-1">
          {analysis.sheets.map((s) => (
            <button key={s.name} role="tab" aria-selected={s.name === sheet.name} onClick={() => setSheetName(s.name)}
              className={`rounded-full px-3.5 py-1.5 text-sm transition-colors ${s.name === sheet.name ? 'bg-white/10 text-ivory shadow-[inset_0_0_0_1px_var(--color-line-strong)]' : 'text-mist hover:text-ivory'}`}>
              {s.name}
            </button>
          ))}
        </div>
        <a href={api.atelier.originalUrl(analysis.id)} className={buttonClass('ghost', 'sm')} download><Download size={14} aria-hidden="true" />{texts.atelier.downloadOriginal}</a>
        <Button size="sm" variant="ghost" onClick={onClose} icon={<X size={14} />}>{texts.atelier.close}</Button>
      </div>

      {/* Réglages */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" data-enter>
        <Field label={texts.atelier.headerRow} hint={busy === 'reload' ? texts.atelier.analyzing : undefined}>
          {({ id }) => <TextInput id={id} type="number" min={1} max={sheet.max_row} value={headerRow} onChange={(e) => reanalyze(Math.max(1, Number(e.target.value) || 1))} />}
        </Field>
        <Field label={texts.atelier.keyColumn}
          badge={sheet.key && sheet.key.column === keyColumn ? <Badge tone="sage" className="!py-0 !text-[0.65rem]">{texts.atelier.detected}</Badge> : undefined}
          hint={sheet.key && sheet.key.column === keyColumn ? texts.atelier.recognized(sheet.key.recognized, sheet.key.total) : undefined}>
          {({ id, describedBy }) => (
            <Select id={id} aria-describedby={describedBy} value={keyColumn} onChange={(e) => setKeyColumn(e.target.value)}>
              <option value="">{texts.automation.selectPlaceholder}</option>
              {sheet.columns.map((c) => <option key={c.letter} value={c.letter}>{c.letter} — {c.header || '(sans en-tête)'}</option>)}
            </Select>
          )}
        </Field>
        <Field label={texts.atelier.keyType}>
          {({ id }) => (
            <Select id={id} value={keyType} onChange={(e) => setKeyType(e.target.value)}>
              <option value="isin_part">ISIN de la part</option>
              <option value="isin_instrument">ISIN de l'instrument</option>
            </Select>
          )}
        </Field>
        <Field label={texts.atelier.asOf}>
          {({ id }) => <TextInput id={id} type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />}
        </Field>
      </div>
      <div className="flex flex-wrap gap-8" data-enter>
        <Switch checked={overwrite} onChange={setOverwrite} label={texts.atelier.overwrite} hint={texts.atelier.overwriteHint} />
        <Switch checked={highlight} onChange={setHighlight} label={texts.atelier.highlight} />
      </div>

      {/* Propositions */}
      {proposals.length > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-[var(--radius-card)] border border-steel-400/30 bg-steel-500/[0.07] p-4" data-enter>
          <Sparkles className="text-steel-300" size={18} aria-hidden="true" />
          <span className="font-medium">{texts.atelier.suggestions} :</span>
          {proposals.map((c) => (
            <button key={c.letter} onClick={() => assign(c.letter, c.proposed!)} className="rounded-full border border-steel-400/40 px-3 py-1 text-sm text-steel-300 hover:bg-steel-500/15">
              {c.letter} « {c.header} » → {byId[c.proposed!]?.label}
            </button>
          ))}
          <Button size="sm" variant="secondary" className="ml-auto"
            onClick={() => setMappings((all) => [...all, ...proposals.map((c) => ({ column: c.letter, extraction: c.proposed! }))])}>
            {texts.atelier.acceptAll}
          </Button>
        </div>
      )}

      {/* Grille + catalogue */}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0" data-enter>
          <SheetGrid sheet={sheet} headerRow={headerRow} keyColumn={keyColumn} mappings={mappings} extractions={byId}
            selectedColumn={selected} onSelectColumn={setSelected} onDrop={assign}
            onRemove={(col) => setMappings((all) => all.filter((m) => m.column !== col))} preview={preview} showAfter={showAfter} />
        </div>
        <div data-enter>
          <ExtractionPanel extractions={extractions} keyType={keyType} selectedColumn={selected}
            usedIds={new Set(mappings.map((m) => m.extraction))}
            onAssign={(id) => selected && assign(selected, id)} />
        </div>
      </div>

      {/* Barre d'actions */}
      <div className="sticky bottom-4 z-30 glass flex flex-wrap items-center gap-3 rounded-[var(--radius-card)] p-4 shadow-[var(--shadow-deep)]">
        {preview ? (
          <div ref={statsRef} className="flex flex-wrap items-center gap-2" aria-live="polite">
            {Object.entries(preview.stats).filter(([, n]) => n > 0).map(([k, n]) => (
              <Badge key={k} tone={k === 'fill' ? 'champagne' : k === 'not_found' ? 'danger' : k === 'unchanged' ? 'sage' : 'muted'}>
                <strong className="tabular-nums">{n}</strong> {texts.atelier.stats[k]}
              </Badge>
            ))}
            <div role="group" aria-label="Avant / après" className="ml-2 inline-flex rounded-full border border-line-strong p-0.5 text-xs">
              {[false, true].map((after) => (
                <button key={String(after)} onClick={() => setShowAfter(after)} aria-pressed={showAfter === after}
                  className={`rounded-full px-3 py-1 ${showAfter === after ? 'bg-white/10 text-ivory' : 'text-mist'}`}>
                  {after ? texts.atelier.after : texts.atelier.before}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-sm text-mist">
            {mappings.length ? `${texts.atelier.mapped} : ${mappings.length}` : texts.atelier.noMapping}
          </p>
        )}
        <div className="ml-auto flex flex-wrap gap-2">
          <Button variant="ghost" onClick={() => setSaveOpen(true)} icon={<Save size={16} />} disabled={!mappings.length || !keyColumn}>{texts.atelier.saveRecipe}</Button>
          <Button variant="ghost" onClick={() => (savedRecipe?.id ? setScheduleOpen(true) : save(true))} icon={<CalendarClock size={16} />} disabled={!mappings.length || !keyColumn}>{texts.atelier.schedule}</Button>
          <Button variant="secondary" onClick={runPreview} loading={busy === 'preview'} icon={<Eye size={16} />} disabled={!mappings.length || !keyColumn}>
            {busy === 'preview' ? texts.atelier.previewing : texts.atelier.preview}
          </Button>
          <Button variant="primary" onClick={execute} loading={busy === 'run'} icon={<Play size={16} />} disabled={!mappings.length || !keyColumn}>{texts.atelier.run}</Button>
        </div>
        {error && (
          <p role="alert" className="basis-full text-sm text-danger">{error.message} <span className="text-mist">{error.hint}</span></p>
        )}
      </div>

      {/* Versions */}
      <section className="glass rounded-[var(--radius-card)] p-6">
        <h2 className="text-2xl">{texts.atelier.versions}</h2>
        {analysis.versions.length === 0 ? (
          <p className="mt-3 text-sm text-mist">{texts.atelier.noVersions}</p>
        ) : (
          <ul className="mt-4 divide-y divide-[var(--color-line)]">
            {analysis.versions.map((v) => (
              <li key={v.name} className="flex flex-wrap items-center gap-3 py-3 text-sm">
                <Badge tone="champagne">v{v.version ?? '?'}</Badge>
                <span className="min-w-0 flex-1 truncate text-mist">{v.name}</span>
                <span className="text-haze">{v.by ?? ''} · {formatRelative(v.created_at)} · {v.written ?? 0} cellule(s)</span>
                <a href={api.atelier.versionUrl(analysis.id, v.name)} download className={buttonClass('secondary', 'sm')}><Download size={14} aria-hidden="true" />{texts.run.download}</a>
              </li>
            ))}
          </ul>
        )}
      </section>

      <Dialog open={saveOpen} onClose={() => setSaveOpen(false)} title={texts.atelier.saveRecipe}
        footer={<>
          <Button variant="ghost" onClick={() => setSaveOpen(false)}>{texts.common.cancel}</Button>
          <Button variant="primary" onClick={() => save()} loading={busy === 'save'} icon={<Save size={16} />}>{texts.common.save}</Button>
        </>}>
        <Field label={texts.atelier.recipeName}>
          {({ id }) => <TextInput id={id} value={recipeName} autoFocus onChange={(e) => setRecipeName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && save()} />}
        </Field>
      </Dialog>
      {savedRecipe?.id && (
        <ScheduleDialog open={scheduleOpen} onClose={() => setScheduleOpen(false)} targetType="recipe" targetId={savedRecipe.id} label={savedRecipe.name} />
      )}
    </div>
  )
}

/* ======================================================================= page */
export default function Atelier() {
  const [analysis, setAnalysis] = useState<WorkbookAnalysis | null>(null)
  const [recipe, setRecipe] = useState<Recipe | null>(null)
  const [loadingRecipe, setLoadingRecipe] = useState(false)
  const catalog = useAsync(() => api.atelier.extractions(), [])
  const root = useRef<HTMLDivElement>(null)

  useGSAP(() => {
    gsap.from('[data-enter]', { opacity: 0, y: dist('enter'), stagger: stagger.base, duration: d('slow'), ease: ease.out })
  }, { scope: root, dependencies: [analysis?.id ?? 'home'], revertOnUpdate: false })

  const openRecipe = async (r: Recipe) => {
    setLoadingRecipe(true)
    try {
      const a = await api.atelier.workbook(r.workbook_id, r.sheet, r.header_row)
      setRecipe(r)
      setAnalysis(a)
    } finally {
      setLoadingRecipe(false)
    }
  }

  return (
    <div ref={root} className="mx-auto w-[min(100%-2rem,90rem)] pt-16">
      <header className="max-w-3xl" data-enter>
        <p className="eyebrow">{texts.atelier.eyebrow}</p>
        <h1 className="mt-4 text-[clamp(2.5rem,6vw,4.5rem)] font-light leading-[0.95]">{texts.atelier.title}</h1>
        {!analysis && <p className="mt-5 text-lg text-mist">{texts.atelier.intro}</p>}
      </header>
      <div className="mt-10">
        {catalog.error && <ErrorState error={catalog.error} onRetry={catalog.reload} />}
        {loadingRecipe && <Loading />}
        {!analysis && !loadingRecipe && <AtelierHome onOpen={(a) => { setRecipe(null); setAnalysis(a) }} onRecipe={openRecipe} />}
        {analysis && catalog.data && (
          <Workbench key={`${analysis.id}-${recipe?.id ?? 'new'}`} analysis={analysis} recipe={recipe} extractions={catalog.data.extractions}
            onClose={() => { setAnalysis(null); setRecipe(null) }} />
        )}
      </div>
    </div>
  )
}
