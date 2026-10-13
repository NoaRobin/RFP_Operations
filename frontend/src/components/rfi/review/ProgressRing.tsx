/** Anneau de complétion : automatique · validée · à vérifier · à compléter. */
import { texts } from '../../../content/texts'
import type { ReviewState } from './state'

const ORDER: { key: ReviewState; color: string }[] = [
  { key: 'auto', color: 'var(--color-mint-400)' },
  { key: 'accepted', color: 'var(--color-magic-400)' },
  { key: 'review', color: 'var(--color-sun-400)' },
  { key: 'none', color: 'var(--color-bubble-400)' },
]

export function ProgressRing({ counts }: { counts: Record<ReviewState, number> }) {
  const total = ORDER.reduce((n, o) => n + counts[o.key], 0) || 1
  const treated = Math.round(((counts.auto + counts.accepted) / total) * 100)
  const r = 42
  const c = 2 * Math.PI * r
  let offset = 0
  return (
    <div className="flex items-center gap-4">
      <svg viewBox="0 0 100 100" className="size-24 shrink-0 -rotate-90" role="img" aria-label={`${treated} % ${texts.review.treated}`}>
        <circle cx="50" cy="50" r={r} fill="none" stroke="var(--color-card-2)" strokeWidth="12" />
        {ORDER.map((o) => {
          const len = (counts[o.key] / total) * c
          const el = (
            <circle key={o.key} cx="50" cy="50" r={r} fill="none" stroke={o.color} strokeWidth="12"
              strokeDasharray={`${len} ${c - len}`} strokeDashoffset={-offset} className="motion-safe:transition-[stroke-dasharray] motion-safe:duration-500" />
          )
          offset += len
          return el
        })}
        <circle cx="50" cy="50" r={r + 6} fill="none" stroke="var(--color-fg)" strokeWidth="2.5" />
        <circle cx="50" cy="50" r={r - 6} fill="none" stroke="var(--color-fg)" strokeWidth="2.5" />
      </svg>
      <div>
        <p className="font-display text-3xl font-bold tabular-nums">{treated} %<span className="ml-1 text-base text-fg-2">{texts.review.treated}</span></p>
        <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs font-bold">
          {ORDER.map((o) => (
            <li key={o.key} className="flex items-center gap-1.5">
              <span className="size-3 rounded-full border-2 border-fg" style={{ background: o.color }} aria-hidden="true" />
              {counts[o.key]} {texts.review.legend[o.key]}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
