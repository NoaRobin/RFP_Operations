import { useLayoutEffect, useRef, type ReactNode } from 'react'
import { RefreshCw } from 'lucide-react'
import { texts, pick } from '../../content/texts'
import { useRotatingMessage } from '../../lib/hooks'
import { gsap } from '../../motion/gsap'
import { d, dist, ease, stagger } from '../../motion/tokens'
import { Button } from './Button'
import type { ApiError } from '../../lib/api'

/** Rune de chargement + messages tournants. */
export function Loading({ label, compact = false }: { label?: string; compact?: boolean }) {
  const message = useRotatingMessage(texts.loading)
  return (
    <div role="status" aria-live="polite" className={`flex items-center gap-4 ${compact ? '' : 'justify-center py-16'}`}>
      <span className="relative inline-block size-9" aria-hidden="true">
        <span className="absolute inset-0 rounded-full border-[3px] border-fg/15" />
        <span className="absolute inset-0 rounded-full border-[3px] border-transparent border-t-magic-500 border-r-bubble-400 animate-spin" />
        <span className="absolute inset-[30%] rounded-full border-2 border-fg bg-sun-400 animate-bounce" />
      </span>
      <span className="font-display text-base font-semibold text-fg-2">{label ?? message}</span>
    </div>
  )
}

export function Skeleton({ className = '' }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`rounded-[var(--radius-card)] border-2 border-fg/15 bg-[linear-gradient(90deg,rgb(255_240_214),rgb(255_255_255),rgb(255_240_214))] bg-[length:200%_100%] animate-shimmer ${className}`}
    />
  )
}

/** État vide mis en scène : une petite constellation, un titre, une action. */
export function EmptyState({ title, body, action, icon }: { title: string; body?: string; action?: ReactNode; icon?: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const ctx = gsap.context(() => {
      gsap.from('[data-anim]', { opacity: 0, y: dist('lift'), stagger: stagger.base, duration: d('slow'), ease: ease.out })
      gsap.to('[data-star]', { opacity: 0.2, duration: 1.6, stagger: { each: 0.3, repeat: -1, yoyo: true }, ease: ease.breathe })
    }, ref)
    return () => ctx.revert()
  }, [])
  return (
    <div ref={ref} className="flex flex-col items-center text-center gap-3 py-14 px-6">
      <div data-anim className="relative mb-2 size-20" aria-hidden="true">
        {icon ?? (
          <svg viewBox="0 0 80 80" className="size-20">
            <circle data-star cx="16" cy="22" r="2" fill="var(--color-sun-300)" />
            <circle data-star cx="58" cy="14" r="1.5" fill="var(--color-magic-300)" />
            <circle data-star cx="66" cy="52" r="2.2" fill="var(--color-mint-400)" />
            <circle data-star cx="28" cy="62" r="1.4" fill="var(--color-sun-300)" />
            <path d="M16 22 L58 14 L66 52 L28 62 Z" fill="none" stroke="var(--color-line-strong)" strokeDasharray="3 4" />
            <path d="M40 30 l2.2 6 6 2.2 -6 2.2 -2.2 6 -2.2 -6 -6 -2.2 6 -2.2z" fill="var(--color-sun-400)" />
          </svg>
        )}
      </div>
      <h3 data-anim className="text-2xl text-fg">{title}</h3>
      {body && <p data-anim className="max-w-md text-fg-2">{body}</p>}
      {action && <div data-anim className="mt-3">{action}</div>}
    </div>
  )
}

/** Erreur : message utile, piste d'action, puis (seulement ensuite) la blague. */
export function ErrorState({ error, onRetry, joke }: { error: ApiError | Error; onRetry?: () => void; joke?: string }) {
  const hint = 'hint' in error ? (error as ApiError).hint : ''
  const isNetwork = error.message === texts.errors.network
  return (
    <div role="alert" className="glass mx-auto my-10 max-w-xl rounded-[var(--radius-card)] p-6 !border-danger">
      <p className="eyebrow !text-danger">{texts.errors.generic}</p>
      <h3 className="mt-2 text-2xl">{error.message}</h3>
      {hint && <p className="mt-2 text-fg-2">{hint}</p>}
      <p className="mt-3 text-sm italic text-fg-3">{joke ?? (isNetwork ? texts.errors.networkJoke : pick(texts.run.errorJokes))}</p>
      {onRetry && (
        <Button className="mt-5" onClick={onRetry} icon={<RefreshCw size={16} />}>{texts.errors.retry}</Button>
      )}
    </div>
  )
}
