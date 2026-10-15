import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Copy, Download, FileSpreadsheet, Pencil, RotateCcw, Square } from 'lucide-react'
import { DataTable } from '../components/run/DataTable'
import { EnergyBar } from '../components/run/EnergyBar'
import { LogPanel } from '../components/run/LogPanel'
import { Timeline } from '../components/run/Timeline'
import { useRunStream } from '../components/run/useRunStream'
import { Stage } from '../components/three/Stage'
import type { Mood } from '../components/three/moods'
import { Button, buttonClass } from '../components/ui/Button'
import { StatusPill } from '../components/ui/StatusPill'
import { useToast } from '../components/ui/Toast'
import { texts, pick } from '../content/texts'
import { api, ApiError } from '../lib/api'
import { formatBytes, formatDateTime, formatDuration } from '../lib/format'
import type { Run } from '../lib/types'
import { gsap, useGSAP } from '../motion/gsap'
import { d, dist, ease, stagger } from '../motion/tokens'

function useElapsed(start: string | null | undefined, running: boolean) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    if (!running) return
    const id = window.setInterval(() => setNow(Date.now()), 250)
    return () => window.clearInterval(id)
  }, [running])
  return start ? Math.max(0, now - new Date(start).getTime()) : 0
}

export default function RunPage() {
  const { runId = '' } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const toast = useToast()
  const seed = (location.state as { run?: Run } | null)?.run
  const { state } = useRunStream(runId, seed)
  const { run, status, steps, logs, progress, outputs, tables, summary, error, hint } = state
  const live = status === 'running' || status === 'queued'
  const elapsed = useElapsed(run?.started_at ?? run?.created_at, live)
  const root = useRef<HTMLDivElement>(null)
  const result = useRef<HTMLDivElement>(null)
  const [busy, setBusy] = useState(false)
  const pokes = useRef(0)

  const mood: Mood = status === 'success' ? 'success' : status === 'error' ? 'failure' : status === 'cancelled' ? 'calm' : 'focus'
  const stepProgress = steps.length ? steps.filter((s) => s.status === 'done').length / steps.length : null
  const title = useMemo(
    () => (status === 'success' ? pick(texts.run.successTitles, runId.charCodeAt(5)) : status === 'error' ? pick(texts.run.errorTitles, runId.charCodeAt(5)) : texts.run.cancelledTitle),
    [status, runId],
  )
  const joke = useMemo(() => pick(texts.run.errorJokes, runId.charCodeAt(6)), [runId])

  useGSAP(() => {
    gsap.from('[data-enter]', { opacity: 0, y: dist('enter'), stagger: stagger.base, duration: d('slow'), ease: ease.out })
  }, { scope: root })

  // Mise en scène du résultat
  useEffect(() => {
    if (live || !result.current) return
    gsap.fromTo(result.current, { opacity: 0, y: dist('enter'), scale: 0.98 }, { opacity: 1, y: 0, scale: 1, duration: d('slow'), ease: ease.spring })
    if (status === 'error') gsap.fromTo(result.current, { x: -6 }, { x: 0, duration: d('slow'), ease: 'elastic.out(1, 0.3)', delay: 0.2 })
  }, [live, status])

  const cancel = async () => {
    setBusy(true)
    try {
      await api.cancel(runId)
    } catch (e) {
      toast('error', (e as ApiError).message, (e as ApiError).hint)
    } finally {
      setBusy(false)
    }
  }

  const retry = async () => {
    if (!run) return
    setBusy(true)
    try {
      const next = run.target_type === 'automation'
        ? await api.run(run.target_id, run.params)
        : await api.atelier.runRecipe(run.target_id)
      navigate(`/executions/${next.id}`, { state: { run: next } })
    } catch (e) {
      toast('error', (e as ApiError).message, (e as ApiError).hint)
    } finally {
      setBusy(false)
    }
  }

  const copyReport = async () => {
    const report = [
      `Automatisation : ${run?.target_name} (${run?.target_id})`, `Exécution : ${runId}`, `Statut : ${status}`,
      `Erreur : ${error ?? ''}`, `Piste : ${hint ?? ''}`, `Paramètres : ${JSON.stringify(run?.params ?? {})}`, '',
      ...logs.map((l) => `${l.ts} [${l.level}] ${l.message}`),
    ].join('\n')
    try {
      await navigator.clipboard.writeText(report)
      toast('success', texts.run.copied)
    } catch {
      toast('error', texts.errors.generic)
    }
  }

  const poke = () => {
    pokes.current += 1
    if (pokes.current % 4 === 0) toast('magic', pick(texts.easterEggs.orb, pokes.current / 4 - 1))
  }

  const back = run?.target_type === 'recipe' ? '/atelier' : run?.target_type === 'rfi' ? '/rfi' : run?.target_type === 'mergecodes' ? '/merge-codes' : run ? `/automatisations/${run.target_id}` : '/'

  return (
    <div ref={root} className="mx-auto w-[min(100%-2rem,82rem)] pt-12">
      <Link to={back} className="inline-flex items-center gap-2 text-sm text-fg-2 hover:text-fg">
        <ArrowLeft size={16} aria-hidden="true" />
        {run?.target_type === 'recipe' ? texts.nav.atelier : texts.automation.back}
      </Link>

      <div className="mt-6 grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
        {/* Scène */}
        <section data-enter className="relative overflow-hidden rounded-[calc(var(--radius-card)*1.4)] glass min-h-[22rem] lg:min-h-[30rem]" aria-label={`${texts.run.eyebrow} : ${texts.run.status[status]}`}>
          <Stage mood={mood} onPoke={poke} className="absolute inset-0" />
          <div className="relative z-10 flex h-full min-h-[22rem] lg:min-h-[30rem] flex-col justify-between p-6 pointer-events-none">
            <div>
              <p className="eyebrow">{texts.run.eyebrow}</p>
              <h1 className="mt-2 text-[clamp(1.9rem,3.5vw,2.75rem)] leading-tight">{run?.target_name ?? '…'}</h1>
            </div>
            <div className="flex flex-wrap items-end justify-between gap-3">
              <StatusPill status={status} className="!text-sm" />
              <p className="font-mono text-sm text-fg-2 tabular-nums" aria-live="off">
                {texts.run.elapsed} · {formatDuration(live ? elapsed : state.durationMs ?? run?.duration_ms ?? elapsed)}
              </p>
            </div>
          </div>
        </section>

        {/* Pilotage */}
        <div className="flex flex-col gap-6">
          <section data-enter className="glass rounded-[var(--radius-card)] p-6">
            <EnergyBar value={progress ?? stepProgress} status={status} label={`Progression de ${run?.target_name ?? 'cette exécution'}`} />
            {state.progressMessage && <p className="mt-2 text-sm text-fg-2">{state.progressMessage}</p>}
            <div className="mt-6 grid gap-6 sm:grid-cols-[1fr_auto]">
              <div>
                <h2 className="mb-4 font-mono text-sm uppercase tracking-[0.2em] text-sun-300">{texts.run.steps}</h2>
                <Timeline steps={steps} />
              </div>
              <dl className="grid content-start gap-3 text-sm sm:min-w-48">
                <div><dt className="text-fg-3">{texts.run.by}</dt><dd className="text-fg">{run?.user ?? '…'}</dd></div>
                <div><dt className="text-fg-3">Lancé</dt><dd className="text-fg">{formatDateTime(run?.created_at)}</dd></div>
                {run && Object.keys(run.params ?? {}).length > 0 && (
                  <div>
                    <dt className="text-fg-3">{texts.run.params}</dt>
                    <dd className="font-mono text-xs text-fg-2">
                      {Object.entries(run.params).filter(([, v]) => v !== null && v !== undefined).map(([k, v]) => <div key={k}>{k} = {String(v)}</div>)}
                    </dd>
                  </div>
                )}
              </dl>
            </div>
            {live && (
              <Button className="mt-6" variant="danger" size="sm" onClick={cancel} loading={busy} icon={<Square size={14} />}>{texts.run.cancel}</Button>
            )}
          </section>

          {!live && (
            <section ref={result} role={status === 'error' ? 'alert' : 'status'}
              className={`rounded-[var(--radius-card)] border p-6 ${status === 'success' ? 'border-sun-400/40 bg-sun-400/[0.06]' : status === 'error' ? 'border-danger/40 bg-danger/[0.07]' : 'border-line-strong bg-fg/[0.03]'}`}>
              <h2 className="text-3xl">{title}</h2>
              {status === 'success' && (
                <>
                  {summary && <p className="mt-2 text-lg text-fg-2">{summary}</p>}
                  {run && <p className="mt-1 text-sm text-sun-300">{texts.run.minutesSaved(run.minutes_saved)}</p>}
                </>
              )}
              {status === 'error' && (
                <>
                  <p className="mt-3 text-lg text-fg">{error}</p>
                  {hint && (
                    <p className="mt-2 text-fg-2"><span className="font-semibold text-fg">{texts.run.whatToDo} </span>{hint}</p>
                  )}
                  <p className="mt-3 text-sm italic text-fg-3">{joke}</p>
                </>
              )}
              {status === 'cancelled' && <p className="mt-2 text-fg-2">{texts.run.cancelledBody}</p>}

              {outputs.length > 0 && (
                <div className="mt-6 flex flex-wrap gap-3">
                  {outputs.map((o) => (
                    <a key={o.name} href={api.fileUrl(runId, o.name)} download className={buttonClass(o.kind === 'excel' ? 'primary' : 'secondary', 'md')}>
                      {o.kind === 'excel' ? <FileSpreadsheet size={18} aria-hidden="true" /> : <Download size={18} aria-hidden="true" />}
                      {o.label}
                      <span className="text-xs opacity-70">{formatBytes(o.size)}</span>
                    </a>
                  ))}
                </div>
              )}
              <div className="mt-6 flex flex-wrap gap-3">
                <Button variant="secondary" onClick={retry} loading={busy} icon={<RotateCcw size={16} />}>{texts.run.retry}</Button>
                {run?.target_type === 'automation' && (
                  <Button variant="ghost" icon={<Pencil size={16} />} onClick={() => navigate(`/automatisations/${run.target_id}`, { state: { params: run.params } })}>{texts.run.edit}</Button>
                )}
                {status === 'error' && <Button variant="ghost" icon={<Copy size={16} />} onClick={copyReport}>{texts.run.copyReport}</Button>}
              </div>
            </section>
          )}
        </div>
      </div>

      <div className="mt-8 grid gap-8">
        <div data-enter><LogPanel logs={logs} live={live} /></div>
        {tables.map((t) => <DataTable key={t.title} title={t.title} columns={t.columns} rows={t.rows} total={t.total_rows} />)}
      </div>
    </div>
  )
}
