/** OMNI mensuel : le process expliqué (avant / maintenant), lancement, programmation mensuelle, derniers contrôles. */
import { useEffect, useRef, useState } from 'react'
import { ArrowRight, CalendarCheck, CalendarClock, CheckCircle2, FolderOpen, Inbox, Play, TriangleAlert } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { ScheduleDialog } from '../components/ScheduleDialog'
import { Button } from '../components/ui/Button'
import { Field, Select, Switch, TextInput } from '../components/ui/Field'
import { ErrorState, Loading } from '../components/ui/States'
import { texts } from '../content/texts'
import { api, ApiError } from '../lib/api'
import type { OmniOverview } from '../lib/types'
import { gsap, useGSAP } from '../motion/gsap'
import { d, ease, prefersReducedMotion } from '../motion/tokens'

const T = texts.omni

export default function Omni() {
  const navigate = useNavigate()
  const root = useRef<HTMLDivElement>(null)
  const [data, setData] = useState<OmniOverview | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [month, setMonth] = useState<number | ''>('')
  const [year, setYear] = useState<number | ''>('')
  const [source, setSource] = useState('fabric')
  const [outlook, setOutlook] = useState(true)
  const [overwrite, setOverwrite] = useState(false)
  const [scheduling, setScheduling] = useState(false)
  const [running, setRunning] = useState(false)

  useEffect(() => {
    api.omni().then((o) => { setData(o); setMonth(o.next.mois); setYear(o.next.annee) }).catch((e) => setError(e))
  }, [])
  useGSAP(() => {
    if (prefersReducedMotion() || !data) return
    gsap.from('[data-enter]', { y: 24, opacity: 0, stagger: 0.07, duration: d('slow'), ease: ease.out })
  }, { scope: root, dependencies: [!!data] })

  const launch = async () => {
    setRunning(true)
    try {
      const run = await api.run('omni_mensuel', { mois: month || null, annee: year || null, holdings: source, outlook, ecraser: overwrite })
      navigate(`/executions/${run.id}`)
    } finally { setRunning(false) }
  }

  if (error) return <div className="mx-auto w-[min(100%-2rem,82rem)] pt-14"><ErrorState error={error} /></div>
  if (!data) return <Loading />
  return (
    <div ref={root} className="mx-auto w-[min(100%-2rem,82rem)] pt-10 sm:pt-14">
      <header data-enter className="max-w-3xl">
        <p className="eyebrow"><CalendarCheck size={13} aria-hidden="true" />{T.eyebrow}</p>
        <h1 className="mt-4 text-[clamp(2.2rem,5.5vw,4rem)] font-bold">{T.title}</h1>
        <p className="mt-4 text-lg font-semibold text-fg-2">{T.lead}</p>
      </header>

      <ol data-enter className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {T.steps.map((s, i) => (
          <li key={s.title} className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-4 shadow-[var(--shadow-pop)]">
            <p className="flex items-center gap-2 font-display text-lg font-semibold">
              <span className="grid size-7 place-items-center rounded-full border-2 border-fg bg-sun-400 text-sm">{i + 1}</span>{s.title}
            </p>
            <p className="mt-2 text-xs font-bold uppercase tracking-wider text-fg-3">{T.before}</p>
            <p className="text-sm font-semibold text-fg-2 line-through decoration-bubble-400/70">{s.before}</p>
            <p className="mt-2 flex items-center gap-1 text-xs font-bold uppercase tracking-wider text-mint-300"><ArrowRight size={12} aria-hidden="true" />{T.after}</p>
            <p className="text-sm font-semibold">{s.after}</p>
          </li>
        ))}
      </ol>

      <section data-enter className="glass mt-8 rounded-[var(--radius-card)] p-5 sm:p-7">
        <p className="font-semibold text-fg-2">{T.next(data.next.periode, data.next.date_arrete, data.next.source)}</p>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label={T.month}>{({ id }) => <TextInput id={id} type="number" min={1} max={12} value={month} onChange={(e) => setMonth(e.target.value ? Number(e.target.value) : '')} />}</Field>
          <Field label={T.year}>{({ id }) => <TextInput id={id} type="number" value={year} onChange={(e) => setYear(e.target.value ? Number(e.target.value) : '')} />}</Field>
          <Field label={T.holdings}>{({ id }) => (
            <Select id={id} value={source} onChange={(e) => setSource(e.target.value)}>
              {Object.entries(T.sources).map(([k, v]) => <option key={k} value={k} disabled={k === 'jump_excel' && !data.jump_excel}>{v}</option>)}
            </Select>
          )}</Field>
          <div className="flex flex-col justify-end gap-2">
            <Switch checked={outlook} onChange={setOutlook} label={T.outlook} />
            <Switch checked={overwrite} onChange={setOverwrite} label={T.overwrite} />
          </div>
        </div>
        <ul className="mt-4 space-y-1 text-sm font-semibold text-fg-2">
          <li className="flex items-center gap-2"><FolderOpen size={15} aria-hidden="true" />{T.root} : <code className="text-xs">{data.root}</code></li>
          <li className="flex items-center gap-2"><Inbox size={15} aria-hidden="true" />{T.inbox} : <code className="text-xs">{data.inbox}</code></li>
          {!data.outlook && <li className="flex items-center gap-2 text-warning"><TriangleAlert size={15} aria-hidden="true" />{T.outlookOff}</li>}
        </ul>
        <div className="mt-5 flex flex-wrap gap-3">
          <Button variant="primary" size="lg" loading={running} onClick={launch} icon={<Play size={18} />}>{T.run}</Button>
          <Button onClick={() => setScheduling(true)} icon={<CalendarClock size={18} />}>{T.schedule}</Button>
        </div>
      </section>

      <section data-enter className="mt-8">
        <h2 className="text-2xl">{T.reports}</h2>
        {data.reports.length === 0 ? <p className="mt-2 font-semibold text-fg-2">{T.noReport}</p> : (
          <ul className="mt-3 grid gap-3 md:grid-cols-2">
            {data.reports.map((r) => (
              <li key={r.file} className="rounded-2xl border-2 border-fg bg-card p-4">
                <p className="flex items-center gap-2 font-display text-lg font-semibold">
                  {r.statut === 'OK' ? <CheckCircle2 size={18} className="text-mint-300" aria-hidden="true" /> : <TriangleAlert size={18} className="text-warning" aria-hidden="true" />}
                  {r.periode} · {r.statut}
                </p>
                <p className="text-xs font-semibold text-fg-3">{r.date_arrete}{r.holdings ? ` · ${T.lines(r.holdings)}` : ''}{r.controle_net ? ` · NET ${r.controle_net}` : ''}</p>
                {r.alertes.length > 0 && <ul className="mt-1 text-xs font-semibold text-warning">{r.alertes.map((a) => <li key={a}>⚠ {a}</li>)}</ul>}
              </li>
            ))}
          </ul>
        )}
      </section>
      <ScheduleDialog open={scheduling} onClose={() => setScheduling(false)} targetType="automation" targetId="omni_mensuel" label={T.scheduleLabel}
        params={{ holdings: 'fabric', outlook: true, ecraser: false }} />
    </div>
  )
}
