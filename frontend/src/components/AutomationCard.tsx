import { Link } from 'react-router-dom'
import { Clock, Star } from 'lucide-react'
import { texts } from '../content/texts'
import type { Automation } from '../lib/types'
import { gsap } from '../motion/gsap'
import { d, ease } from '../motion/tokens'
import { SpellIcon } from './ui/Icon'
import { Badge } from './ui/StatusPill'
import { useTilt } from './ui/useTilt'

export function AutomationCard({ automation, favorite, onToggleFavorite }: {
  automation: Automation
  favorite: boolean
  onToggleFavorite: () => void
}) {
  const ref = useTilt<HTMLElement>()
  const a = automation

  return (
    <article
      ref={ref}
      data-card={a.id}
      className="halo group relative flex h-full flex-col rounded-[var(--radius-card)] glass p-6 transition-[border-color,box-shadow] duration-[var(--duration-base)] hover:border-violet-400/40 hover:shadow-[var(--shadow-glow-violet)] focus-within:border-violet-400/50"
    >
      <div className="flex items-start justify-between gap-4" style={{ transform: 'translateZ(30px)' }}>
        <div
          data-flip-id={`icon-${a.id}`}
          className="grid size-14 place-items-center rounded-2xl border border-gold-400/30 bg-[radial-gradient(circle_at_30%_25%,rgb(245_223_165/0.25),rgb(91_33_182/0.25)_60%,transparent)] text-gold-300 shadow-[inset_0_0_20px_rgb(167_139_250/0.25)]"
        >
          <SpellIcon name={a.icon} size={26} strokeWidth={1.6} />
        </div>
        <button
          type="button"
          onClick={(e) => {
            onToggleFavorite()
            const icon = e.currentTarget.querySelector('svg')
            if (icon) gsap.fromTo(icon, { scale: 0.6, rotate: -30 }, { scale: 1, rotate: 0, duration: d('slow'), ease: ease.spring })
          }}
          aria-pressed={favorite}
          aria-label={`${favorite ? texts.grimoire.unfavorite : texts.grimoire.favorite} : ${a.name}`}
          className={`relative z-10 grid size-10 place-items-center rounded-full transition-colors ${favorite ? 'text-gold-300' : 'text-haze hover:text-gold-300'}`}
        >
          <Star size={20} fill={favorite ? 'currentColor' : 'none'} />
        </button>
      </div>

      <p className="mt-6 eyebrow !text-violet-300">{a.category}</p>
      <h3 className="mt-2 text-2xl leading-tight">
        <Link
          to={`/sorts/${a.id}`}
          state={{ preview: a }}
          data-flip-id={`title-${a.id}`}
          className="outline-none after:absolute after:inset-0 after:rounded-[var(--radius-card)] after:content-[''] focus-visible:after:outline focus-visible:after:outline-2 focus-visible:after:outline-arcane-400"
        >
          {a.name}
        </Link>
      </h3>
      <p className="mt-3 line-clamp-3 text-[0.95rem] leading-relaxed text-mist">{a.description}</p>

      <div className="mt-auto flex flex-wrap items-center gap-2 pt-6 text-xs text-haze">
        <Badge tone="gold"><Clock size={12} aria-hidden="true" />{texts.grimoire.minutesSaved(a.estimated_minutes_saved)}</Badge>
        <Badge tone="muted">{texts.grimoire.types[a.type] ?? a.type}</Badge>
        {!a.healthy && <Badge tone="danger">{texts.grimoire.broken}</Badge>}
        <span className="ml-auto">{texts.grimoire.runs(a.stats?.runs ?? 0)}</span>
      </div>
    </article>
  )
}
