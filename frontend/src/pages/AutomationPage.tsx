import { useMemo, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, CalendarClock, ChevronDown, Clock, Database, Globe, Sparkles, TriangleAlert, WandSparkles } from 'lucide-react'
import { ParamField } from '../components/ParamField'
import { ScheduleDialog } from '../components/ScheduleDialog'
import { Button } from '../components/ui/Button'
import { SpellIcon } from '../components/ui/Icon'
import { ErrorState, Loading } from '../components/ui/States'
import { Badge, StatusPill } from '../components/ui/StatusPill'
import { texts } from '../content/texts'
import { api, ApiError } from '../lib/api'
import { formatDuration, formatRelative, todayIso } from '../lib/format'
import { useAsync } from '../lib/hooks'
import type { Automation, ParamSpec } from '../lib/types'
import { gsap, useGSAP } from '../motion/gsap'
import { d, dist, ease, stagger } from '../motion/tokens'

function initialValue(spec: ParamSpec, previous?: Record<string, unknown>) {
  if (previous && spec.name in previous && previous[spec.name] !== null) return previous[spec.name]
  if (spec.type === 'date' && spec.default === 'today') return todayIso()
  if (spec.type === 'multiselect') return Array.isArray(spec.default) ? spec.default : []
  return spec.default ?? (spec.type === 'boolean' ? false : null)
}

function SpellForm({ automation, previous }: { automation: Automation; previous?: Record<string, unknown> }) {
  const navigate = useNavigate()
  const [values, setValues] = useState<Record<string, unknown>>(() =>
    Object.fromEntries(automation.params.map((p) => [p.name, initialValue(p, previous)])),
  )
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [submitError, setSubmitError] = useState<ApiError | null>(null)
  const [launching, setLaunching] = useState(false)
  const [schedule, setSchedule] = useState(false)
  const button = useRef<HTMLDivElement>(null)

  const validate = () => {
    const next: Record<string, string> = {}
    for (const p of automation.params) {
      const v = values[p.name]
      if (p.required && (v === null || v === undefined || v === '' || (Array.isArray(v) && !v.length))) next[p.name] = `${p.label} : ${texts.automation.required}.`
    }
    setErrors(next)
    return Object.keys(next).length === 0
  }

  const launch = async () => {
    if (!validate()) {
      gsap.fromTo(button.current, { x: -8 }, { x: 0, duration: d('slow'), ease: 'elastic.out(1, 0.3)' })
      return
    }
    setLaunching(true)
    setSubmitError(null)
    try {
      const run = await api.run(automation.id, values)
      navigate(`/executions/${run.id}`, { state: { run } })
    } catch (e) {
      setSubmitError(e as ApiError)
      setLaunching(false)
    }
  }

  // Pour la planification, une date égale à aujourd'hui devient « today » (recalculée à chaque exécution).
  const scheduleParams = useMemo(
    () => Object.fromEntries(Object.entries(values).map(([k, v]) => {
      const spec = automation.params.find((p) => p.name === k)
      return [k, spec?.type === 'date' && v === todayIso() ? 'today' : v]
    })),
    [values, automation.params],
  )

  return (
    <form
      noValidate
      onSubmit={(e) => {
        e.preventDefault()
        launch()
      }}
      className="glass rounded-[var(--radius-card)] p-6 sm:p-8"
      data-enter
    >
      <h2 className="text-2xl">{texts.automation.paramsTitle}</h2>
      <div className="mt-6 flex flex-col gap-5">
        {automation.params.length === 0 && <p className="text-fg-2">{texts.automation.noParams}</p>}
        {automation.params.map((spec) => (
          <ParamField key={spec.name} automationId={automation.id} spec={spec} value={values[spec.name]} error={errors[spec.name]}
            onChange={(v) => {
              setValues((all) => ({ ...all, [spec.name]: v }))
              setErrors((all) => ({ ...all, [spec.name]: '' }))
            }} />
        ))}
      </div>
      {submitError && (
        <div role="alert" className="mt-6 rounded-xl border border-danger/40 bg-danger/10 p-4">
          <p className="font-semibold text-danger">{submitError.message}</p>
          {submitError.hint && <p className="mt-1 text-sm text-fg-2">{submitError.hint}</p>}
        </div>
      )}
      <div ref={button} className="mt-8 flex flex-wrap items-center gap-3">
        <Button type="submit" variant="primary" size="lg" loading={launching} disabled={!automation.healthy} icon={<WandSparkles size={18} />}>
          {launching ? texts.automation.launching : texts.automation.launch}
        </Button>
        <Button type="button" variant="secondary" size="lg" disabled={!automation.healthy} onClick={() => setSchedule(true)} icon={<CalendarClock size={18} />}>
          {texts.automation.schedule}
        </Button>
      </div>
      <ScheduleDialog open={schedule} onClose={() => setSchedule(false)} targetType="automation" targetId={automation.id}
        label={automation.name} params={scheduleParams} />
    </form>
  )
}

export default function AutomationPage() {
  const { id = '' } = useParams()
  const location = useLocation()
  const preview = (location.state as { preview?: Automation; params?: Record<string, unknown> } | null)?.preview
  const previousParams = (location.state as { params?: Record<string, unknown> } | null)?.params
  const { data, error, reload } = useAsync(() => api.automation(id), [id])
  const automation = data ?? (preview?.id === id ? preview : undefined)
  const [showSql, setShowSql] = useState(false)
  const root = useRef<HTMLDivElement>(null)

  useGSAP(
    () => {
      if (!data) return
      gsap.from('[data-enter]', { opacity: 0, y: dist('enter'), stagger: stagger.loose, duration: d('slow'), ease: ease.out, delay: 0.15 })
    },
    { scope: root, dependencies: [!!data] },
  )

  if (error) return <ErrorState error={error} onRetry={reload} />
  if (!automation) return <Loading />

  return (
    <div ref={root} className="mx-auto w-[min(100%-2rem,72rem)] pt-12">
      <Link to="/" className="inline-flex items-center gap-2 text-sm text-fg-2 hover:text-fg">
        <ArrowLeft size={16} aria-hidden="true" />
        {texts.automation.back}
      </Link>

      <header className="mt-8 flex flex-col gap-6 sm:flex-row sm:items-start">
        <div data-flip-id={`icon-${automation.id}`}
          className="grid size-20 shrink-0 place-items-center rounded-3xl border border-sun-400/40 bg-[radial-gradient(circle_at_30%_25%,rgb(227_207_161/0.3),rgb(52_80_111/0.3)_60%,transparent)] text-sun-300 shadow-[var(--shadow-glow-sun)]">
          <SpellIcon name={automation.icon} size={38} strokeWidth={1.5} />
        </div>
        <div className="min-w-0">
          <p className="eyebrow !text-magic-300">{automation.category}</p>
          <h1 data-flip-id={`title-${automation.id}`} className="mt-2 text-[clamp(2.25rem,5vw,3.75rem)] font-bold leading-none">{automation.name}</h1>
          <p className="mt-4 max-w-3xl text-lg text-fg-2">{automation.description}</p>
          <div className="mt-5 flex flex-wrap gap-2">
            <Badge tone="sun"><Clock size={12} aria-hidden="true" />{texts.library.minutesSaved(automation.estimated_minutes_saved)}</Badge>
            <Badge tone="muted">{texts.library.types[automation.type]}</Badge>
            {automation.requires.map((r) => (
              <Badge key={r} tone="mint">{r === 'browser' ? <Globe size={12} aria-hidden="true" /> : <Database size={12} aria-hidden="true" />}{texts.automation.needs[r] ?? r}</Badge>
            ))}
            {automation.tags.map((t) => <Badge key={t} tone="magic">#{t}</Badge>)}
          </div>
        </div>
      </header>

      {!automation.healthy && (
        <div role="alert" className="mt-8 rounded-[var(--radius-card)] border border-danger/40 bg-danger/10 p-5">
          <p className="flex items-center gap-2 font-semibold text-danger"><TriangleAlert size={18} aria-hidden="true" />{texts.automation.unhealthyTitle}</p>
          <p className="mt-1 text-fg-2">{texts.automation.unhealthyBody}</p>
          <ul className="mt-2 list-disc pl-6 font-mono text-sm text-fg-3">{automation.problems.map((p) => <li key={p}>{p}</li>)}</ul>
        </div>
      )}

      <div className="mt-10 grid gap-8 lg:grid-cols-[1.4fr_1fr]">
        {data ? <SpellForm automation={data} previous={previousParams} /> : <Loading compact />}

        <aside className="flex flex-col gap-6">
          {automation.outputs.length > 0 && (
            <section className="glass rounded-[var(--radius-card)] p-6" data-enter>
              <h2 className="text-xl">{texts.automation.outputs}</h2>
              <ul className="mt-4 space-y-2 text-fg-2">
                {automation.outputs.map((o) => (
                  <li key={o.label} className="flex items-center gap-2"><Sparkles size={14} className="text-sun-300" aria-hidden="true" />{o.label}</li>
                ))}
              </ul>
            </section>
          )}
          <section className="glass rounded-[var(--radius-card)] p-6" data-enter>
            <h2 className="text-xl">{texts.automation.recent}</h2>
            {!data?.recent_runs?.length ? (
              <p className="mt-3 text-fg-2">{texts.automation.noRecent}</p>
            ) : (
              <ul className="mt-4 divide-y divide-[var(--color-line)]">
                {data.recent_runs.map((r) => (
                  <li key={r.id}>
                    <Link to={`/executions/${r.id}`} className="flex items-center gap-3 py-3 text-sm hover:text-fg">
                      <StatusPill status={r.status} />
                      <span className="truncate text-fg-2">{r.user}</span>
                      <span className="ml-auto shrink-0 text-fg-3">{formatRelative(r.created_at)} · {formatDuration(r.duration_ms)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
          {data?.query && (
            <section className="glass rounded-[var(--radius-card)] p-6" data-enter>
              <button onClick={() => setShowSql((s) => !s)} aria-expanded={showSql}
                className="flex w-full items-center justify-between text-left text-xl font-display">
                {showSql ? texts.automation.hideFormula : texts.automation.formula}
                <ChevronDown className={`transition-transform duration-[var(--duration-base)] ${showSql ? 'rotate-180' : ''}`} size={20} aria-hidden="true" />
              </button>
              {showSql && (
                <pre className="mt-4 max-h-96 overflow-auto rounded-xl bg-field/80 p-4 font-mono text-xs leading-relaxed text-mint-300">{data.query.trim()}</pre>
              )}
            </section>
          )}
        </aside>
      </div>
    </div>
  )
}
