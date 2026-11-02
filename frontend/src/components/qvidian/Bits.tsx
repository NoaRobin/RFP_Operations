/** Petites pièces partagées de la section Qvidian : niveau (société / fonds / part), surlignage, barres, temps relatif. */
import type { ReactNode } from 'react'
import { Building2, Compass, Layers, Ticket, Globe2 } from 'lucide-react'
import type { QvidianLevel } from '../../lib/types'

const SCOPE_STYLE: Record<string, string> = {
  societe: 'bg-magic-400/35', strategie: 'bg-sun-400/60', fonds: 'bg-mint-400/55', part: 'bg-bubble-400/40', generique: 'bg-card-3',
}
const SCOPE_ICON: Record<string, typeof Building2> = { societe: Building2, strategie: Compass, fonds: Layers, part: Ticket, generique: Globe2 }

export function LevelBadge({ level, compact = false }: { level: QvidianLevel; compact?: boolean }) {
  const Icon = SCOPE_ICON[level.scope] ?? Globe2
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <span title={level.clues.join(' · ') || undefined}
        className={`inline-flex items-center gap-1 rounded-full border-2 border-fg px-2 py-0.5 text-[0.7rem] font-bold ${SCOPE_STYLE[level.scope] ?? 'bg-card-3'}`}>
        <Icon size={12} aria-hidden="true" />{level.scope_label}
      </span>
      {level.funds.slice(0, compact ? 1 : 2).map((f) => (
        <span key={f} className="rounded-full border-2 border-fg/40 bg-card px-2 py-0.5 text-[0.7rem] font-bold">{f}</span>
      ))}
      {!compact && level.theme_labels.map((t) => (
        <span key={t} className="rounded-full bg-card-2 px-2 py-0.5 text-[0.7rem] font-semibold text-fg-2">{t}</span>
      ))}
    </span>
  )
}

export function Highlight({ text, spans }: { text: string; spans: [number, number][] }) {
  if (!spans.length) return <>{text}</>
  const out: ReactNode[] = []
  let at = 0
  const sorted = [...spans].sort((a, b) => a[0] - b[0])
  sorted.forEach(([a, b], i) => {
    if (a < at) return
    out.push(text.slice(at, a))
    out.push(<mark key={i} className="rounded bg-sun-400/70 px-0.5 text-fg">{text.slice(a, b)}</mark>)
    at = b
  })
  out.push(text.slice(at))
  return <>{out}</>
}

export function Bar({ value, tone = 'bg-magic-400', label }: { value: number; tone?: string; label?: string }) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)))
  return (
    <span className="inline-flex w-full items-center gap-2" title={label}>
      <span className="h-2.5 flex-1 overflow-hidden rounded-full border-2 border-fg/40 bg-card-2">
        <span className={`block h-full ${tone}`} style={{ width: `${Math.max(pct, 3)}%` }} />
      </span>
    </span>
  )
}

export function ScoreRing({ score, size = 56 }: { score: number; size?: number }) {
  const r = (size - 8) / 2
  const c = 2 * Math.PI * r
  const tone = score >= 70 ? 'var(--color-mint-400)' : score >= 45 ? 'var(--color-sun-400)' : 'var(--color-bubble-400)'
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`Pertinence ${score} sur 100`} className="shrink-0">
      <circle cx={size / 2} cy={size / 2} r={r} fill="var(--color-card)" stroke="var(--color-fg)" strokeOpacity={0.15} strokeWidth={6} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={tone} strokeWidth={6} strokeLinecap="round"
        strokeDasharray={`${(c * score) / 100} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle" className="fill-[var(--color-fg)] font-display text-[15px] font-bold">{score}</text>
    </svg>
  )
}

export function ago(day: string | null | undefined): string {
  if (!day) return 'jamais'
  const d = new Date(day.slice(0, 10))
  if (Number.isNaN(d.getTime())) return day
  const days = Math.round((Date.now() - d.getTime()) / 86_400_000)
  if (days <= 0) return "aujourd'hui"
  if (days < 31) return `il y a ${days} j`
  if (days < 365) return `il y a ${Math.round(days / 30)} mois`
  const y = Math.floor(days / 365)
  return `il y a ${y} an${y > 1 ? 's' : ''}`
}

export function Kpi({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="rounded-2xl border-2 border-fg bg-card p-3" title={hint}>
      <p className="text-[0.7rem] font-bold uppercase tracking-wider text-fg-3">{label}</p>
      <p className="mt-1 font-display text-2xl font-semibold tabular-nums">{value}</p>
    </div>
  )
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
