import type { RunStatus } from '../../lib/types'
import { texts } from '../../content/texts'

const STYLES: Record<RunStatus, string> = {
  queued: 'text-fg-2 border-line-strong bg-fg/5',
  running: 'text-mint-300 border-mint-400/50 bg-mint-400/10',
  success: 'text-success border-success/40 bg-success/10',
  error: 'text-danger border-danger/40 bg-danger/10',
  cancelled: 'text-fg-3 border-line-strong bg-fg/5',
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

export function Badge({ children, tone = 'magic', className = '' }: { children: React.ReactNode; tone?: 'magic' | 'sun' | 'mint' | 'muted' | 'danger'; className?: string }) {
  const tones = {
    magic: 'text-magic-300 border-magic-400/30 bg-magic-500/10',
    sun: 'text-sun-300 border-sun-400/35 bg-sun-400/10',
    mint: 'text-mint-300 border-mint-400/35 bg-mint-400/10',
    muted: 'text-fg-2 border-line-strong bg-fg/5',
    danger: 'text-danger border-danger/40 bg-danger/10',
  }
  return <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium ${tones[tone]} ${className}`}>{children}</span>
}
