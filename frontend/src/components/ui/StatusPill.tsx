import type { RunStatus } from '../../lib/types'
import { texts } from '../../content/texts'

const STYLES: Record<RunStatus, string> = {
  queued: 'text-mist border-line-strong bg-white/5',
  running: 'text-arcane-300 border-arcane-400/50 bg-arcane-400/10',
  success: 'text-success border-success/40 bg-success/10',
  error: 'text-danger border-danger/40 bg-danger/10',
  cancelled: 'text-haze border-line-strong bg-white/5',
}

export function StatusPill({ status, className = '' }: { status: RunStatus; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${STYLES[status]} ${className}`}>
      <span
        aria-hidden="true"
        className={`size-1.5 rounded-full bg-current ${status === 'running' || status === 'queued' ? 'animate-pulse' : ''}`}
      />
      {texts.run.status[status]}
    </span>
  )
}

export function Badge({ children, tone = 'violet', className = '' }: { children: React.ReactNode; tone?: 'violet' | 'gold' | 'arcane' | 'muted' | 'danger'; className?: string }) {
  const tones = {
    violet: 'text-violet-300 border-violet-400/30 bg-violet-500/10',
    gold: 'text-gold-300 border-gold-400/35 bg-gold-400/10',
    arcane: 'text-arcane-300 border-arcane-400/35 bg-arcane-400/10',
    muted: 'text-mist border-line-strong bg-white/5',
    danger: 'text-danger border-danger/40 bg-danger/10',
  }
  return <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium ${tones[tone]} ${className}`}>{children}</span>
}
