import { useLayoutEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, CalendarClock, Info, Pause, Play, Trash2, Trophy, XCircle } from 'lucide-react'
import { Button } from '../components/ui/Button'
import { CountUp } from '../components/ui/CountUp'
import { EmptyState, ErrorState, Loading } from '../components/ui/States'
import { Badge, StatusPill } from '../components/ui/StatusPill'
import { useTilt } from '../components/ui/useTilt'
import { texts } from '../content/texts'
import { api } from '../lib/api'
import { formatDateTime, formatDuration, formatRelative } from '../lib/format'
import { useAsync, useEventSource } from '../lib/hooks'
import type { Dashboard as DashboardData } from '../lib/types'
import { gsap, useGSAP } from '../motion/gsap'
import { d, dist, ease, stagger } from '../motion/tokens'

function Stat({ label, children, accent = false }: { label: string; children: React.ReactNode; accent?: boolean }) {
  const ref = useTilt<HTMLDivElement>(4)
  return (
    <div ref={ref} data-enter className={`halo glass rounded-[var(--radius-card)] p-6 ${accent ? 'border-gold-400/30' : ''}`}>
      <p className="text-sm text-mist">{label}</p>
      <p className={`mt-3 font-display text-5xl font-light ${accent ? 'text-gradient-gold' : 'text-parchment'}`}>{children}</p>
    </div>
  )
}

function ActivityChart({ data }: { data: DashboardData['activity'] }) {
  const ref = useRef<SVGSVGElement>(null)
  const max = Math.max(1, ...data.map((d) => d.success + d.error))
  const width = 700
  const height = 180
  const bar = width / data.length
  useLayoutEffect(() => {
    if (!ref.current) return
    gsap.from(ref.current.querySelectorAll('[data-bar]'), { scaleY: 0, transformOrigin: '50% 100%', duration: d('slow'), ease: ease.out, stagger: stagger.tight })
  }, [data])
  return (
    <figure>
      <svg ref={ref} viewBox={`0 0 ${width} ${height + 24}`} className="w-full" role="img" aria-labelledby="activity-desc">
        <desc id="activity-desc">
          {data.map((d) => `${new Date(d.day).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })} : ${d.success} réussis, ${d.error} en échec`).join(' ; ')}
        </desc>
        <defs>
          <linearGradient id="bar-ok" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#f5dfa5" /><stop offset="1" stopColor="#8b5cf6" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75, 1].map((f) => (
          <line key={f} x1="0" x2={width} y1={height - f * height} y2={height - f * height} stroke="rgba(196,181,253,0.08)" />
        ))}
        {data.map((day, i) => {
          const okH = (day.success / max) * (height - 8)
          const koH = (day.error / max) * (height - 8)
          const x = i * bar + bar * 0.2
          const w = bar * 0.6
          return (
            <g key={day.day}>
              <rect data-bar x={x} y={height - okH} width={w} height={okH} rx="4" fill="url(#bar-ok)" />
              {koH > 0 && <rect data-bar x={x} y={height - okH - koH - 2} width={w} height={koH} rx="4" fill="#fb7185" opacity="0.85" />}
              <text x={x + w / 2} y={height + 18} textAnchor="middle" fontSize="11" fill="#938bb5">{new Date(day.day).getDate()}</text>
            </g>
          )
        })}
      </svg>
      <figcaption className="mt-3 flex gap-4 text-xs text-haze">
        <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm bg-gradient-to-b from-gold-300 to-violet-500" aria-hidden="true" />{texts.dashboard.activityLegendOk}</span>
        <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm bg-danger" aria-hidden="true" />{texts.dashboard.activityLegendKo}</span>
      </figcaption>
    </figure>
  )
}

const ALERT_ICON = { info: Info, warning: AlertTriangle, error: XCircle }
const ALERT_TONE = { info: 'text-info border-info/30 bg-info/5', warning: 'text-warning border-warning/30 bg-warning/5', error: 'text-danger border-danger/30 bg-danger/5' }

export default function Dashboard() {
  const { data, error, loading, reload } = useAsync(() => api.dashboard(), [])
  const root = useRef<HTMLDivElement>(null)
  const pending = useRef<number | null>(null)

  // Mise à jour en direct quand un sort démarre ou se termine (regroupée).
  useEventSource('/api/stream', () => {
    if (pending.current) return
    pending.current = window.setTimeout(() => {
      pending.current = null
      reload()
    }, 800)
  })

  useGSAP(() => {
    if (!data) return
    gsap.from('[data-enter]', { opacity: 0, y: dist('enter'), stagger: stagger.base, duration: d('slow'), ease: ease.out })
  }, { scope: root, dependencies: [!!data] })

  if (error) return <ErrorState error={error} onRetry={reload} />
  if (loading && !data) return <Loading />
  if (!data) return null
  const c = data.counters

  return (
    <div ref={root} className="mx-auto w-[min(100%-2rem,82rem)] pt-16">
      <header data-enter>
        <p className="eyebrow">{texts.dashboard.eyebrow}</p>
        <h1 className="mt-4 text-[clamp(2.5rem,6vw,4.5rem)] font-light leading-none">{texts.dashboard.title}</h1>
      </header>

      {data.has_demo_history && (
        <div data-enter className="mt-8 flex flex-wrap items-center gap-3 rounded-[var(--radius-card)] border border-gold-400/30 bg-gold-400/[0.06] px-5 py-3 text-sm">
          <Info size={16} className="text-gold-300" aria-hidden="true" />
          <span className="text-mist">{texts.dashboard.demoHistory}</span>
          <Button size="sm" variant="ghost" className="ml-auto" onClick={async () => { await api.clearDemo(); reload() }}>{texts.dashboard.clearDemo}</Button>
        </div>
      )}

      <div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label={texts.dashboard.spells}><CountUp value={c.spells_total} /></Stat>
        <Stat label={texts.dashboard.week}><CountUp value={c.spells_week} /></Stat>
        <Stat label={texts.dashboard.saved} accent><CountUp value={c.minutes_saved_total / 60} digits={1} suffix={` ${texts.dashboard.hours}`} /></Stat>
        <Stat label={texts.dashboard.successRate}>{c.success_rate === null ? '—' : <CountUp value={c.success_rate * 100} suffix=" %" />}</Stat>
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <section data-enter className="glass rounded-[var(--radius-card)] p-6">
          <h2 className="text-2xl">{texts.dashboard.activity}</h2>
          <div className="mt-6"><ActivityChart data={data.activity} /></div>
        </section>
        <section data-enter className="glass rounded-[var(--radius-card)] p-6">
          <h2 className="text-2xl">{texts.dashboard.alerts}</h2>
          {data.alerts.length === 0 ? <p className="mt-3 text-mist">{texts.dashboard.noAlerts}</p> : (
            <ul className="mt-4 flex flex-col gap-3">
              {data.alerts.map((a, i) => {
                const Icon = ALERT_ICON[a.level]
                return (
                  <li key={i} className={`rounded-xl border p-3 ${ALERT_TONE[a.level]}`}>
                    <p className="flex items-center gap-2 font-medium"><Icon size={16} aria-hidden="true" />{a.title}</p>
                    {a.detail && <p className="mt-1 text-sm text-mist">{a.detail}</p>}
                    {a.run_id && <Link to={`/executions/${a.run_id}`} className="mt-1 inline-block text-sm text-parchment underline underline-offset-4">Voir l'exécution</Link>}
                  </li>
                )
              })}
            </ul>
          )}
        </section>
      </div>

      <div className="mt-6 grid items-start gap-6 lg:grid-cols-3">
        <section data-enter className="glass rounded-[var(--radius-card)] p-6">
          <h2 className="flex items-center gap-2 text-2xl">{texts.dashboard.running}<Badge tone="arcane">{c.running}</Badge></h2>
          {data.running.length === 0 ? <p className="mt-3 text-mist">{texts.dashboard.noRunning}</p> : (
            <ul className="mt-4 flex flex-col gap-2">
              {data.running.filter(Boolean).map((r) => (
                <li key={r.id}>
                  <Link to={`/executions/${r.id}`} className="flex items-center gap-3 rounded-xl border border-arcane-400/30 bg-arcane-400/[0.06] p-3 hover:bg-arcane-400/10">
                    <StatusPill status={r.status} />
                    <span className="truncate">{r.target_name}</span>
                    <span className="ml-auto text-xs text-haze">{r.user}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section data-enter className="glass rounded-[var(--radius-card)] p-6">
          <h2 className="flex items-center gap-2 text-2xl"><CalendarClock size={22} className="text-gold-300" aria-hidden="true" />{texts.dashboard.scheduled}</h2>
          <ScheduleList onChange={reload} />
        </section>

        <section data-enter className="glass rounded-[var(--radius-card)] p-6">
          <h2 className="flex items-center gap-2 text-2xl"><Trophy size={22} className="text-gold-300" aria-hidden="true" />{texts.dashboard.team}</h2>
          {data.team.length === 0 ? <p className="mt-3 text-mist">{texts.dashboard.noTeam}</p> : (
            <ol className="mt-4 flex flex-col gap-2">
              {data.team.map((t, i) => (
                <li key={t.user} className="flex items-center gap-3 rounded-xl px-2 py-2">
                  <span className={`grid size-8 place-items-center rounded-full font-display text-sm ${i === 0 ? 'bg-gold-300 text-abyss' : i === 1 ? 'bg-violet-300/80 text-abyss' : i === 2 ? 'bg-arcane-400/70 text-abyss' : 'bg-white/5 text-mist'}`}>{i + 1}</span>
                  <span className="truncate">{t.user}</span>
                  <span className="ml-auto text-sm text-gold-300 tabular-nums">{texts.dashboard.minutes(t.minutes_saved)}</span>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>

      <section data-enter className="mt-6 glass rounded-[var(--radius-card)] p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-2xl">{texts.dashboard.recent}</h2>
          <Link to="/historique" className="text-sm text-mist hover:text-parchment">{texts.common.seeAll} →</Link>
        </div>
        {data.recent.length === 0 ? <EmptyState title={texts.history.empty} /> : (
          <ul className="mt-4 divide-y divide-[var(--color-line)]">
            {data.recent.map((r) => (
              <li key={r.id}>
                <Link to={`/executions/${r.id}`} className="flex flex-wrap items-center gap-3 py-3 text-sm hover:text-parchment">
                  <StatusPill status={r.status} />
                  <span className="font-medium">{r.target_name}</span>
                  <span className="text-mist">{r.user}</span>
                  <span className="ml-auto text-haze">{formatRelative(r.created_at)} · {formatDuration(r.duration_ms)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

function ScheduleList({ onChange }: { onChange: () => void }) {
  const { data, reload } = useAsync(() => api.schedules(), [])
  if (!data) return <Loading compact />
  if (data.length === 0) return <p className="mt-3 text-mist">{texts.dashboard.noScheduled}</p>
  return (
    <ul className="mt-4 flex flex-col gap-3">
      {data.map((s) => (
        <li key={s.id} className={`rounded-xl border p-3 ${s.enabled ? 'border-line-strong' : 'border-line opacity-70'}`}>
          <p className="font-medium">{s.label}</p>
          <p className="text-xs text-mist">{s.description}</p>
          <p className="mt-1 text-xs text-haze">{s.enabled ? `${texts.schedule.next} : ${formatDateTime(s.next_run)}` : texts.schedule.disabled}</p>
          <div className="mt-2 flex gap-1">
            <Button size="sm" variant="ghost" icon={s.enabled ? <Pause size={14} /> : <Play size={14} />}
              onClick={async () => { await api.toggleSchedule(s.id, !s.enabled); reload(); onChange() }}>
              {s.enabled ? texts.schedule.pause : texts.schedule.resume}
            </Button>
            <Button size="sm" variant="ghost" aria-label={`${texts.schedule.delete} : ${s.label}`} icon={<Trash2 size={14} />}
              onClick={async () => {
                if (!window.confirm(texts.common.confirmDelete)) return
                await api.deleteSchedule(s.id)
                reload()
                onChange()
              }} />
          </div>
        </li>
      ))}
    </ul>
  )
}
