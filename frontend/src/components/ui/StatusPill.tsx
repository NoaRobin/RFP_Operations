import type { RunStatus } from '../../lib/types'
import { texts } from '../../content/texts'

const STYLES: Record<RunStatus, string> = {
  queued: 'text-mist border-line-strong bg-white/5',
  running: 'text-sage-300 border-sage-400/50 bg-sage-400/10',
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

export function Badge({ children, tone = 'steel', className = '' }: { children: React.ReactNode; tone?: 'steel' | 'champagne' | 'sage' | 'muted' | 'danger'; className?: string }) {
  const tones = {
    steel: 'text-steel-300 border-steel-400/30 bg-steel-500/10',
    champagne: 'text-champagne-300 border-champagne-400/35 bg-champagne-400/10',
    sage: 'text-sage-300 border-sage-400/35 bg-sage-400/10',
    muted: 'text-mist border-line-strong bg-white/5',
    danger: 'text-danger border-danger/40 bg-danger/10',
  }
  return <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium ${tones[tone]} ${className}`}>{children}</span>
}
