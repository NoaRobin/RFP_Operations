import { forwardRef, useRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { Link, type LinkProps } from 'react-router-dom'
import { gsap } from '../../motion/gsap'
import { d, ease } from '../../motion/tokens'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md' | 'lg'

const base =
  'relative inline-flex items-center justify-center gap-2 font-semibold select-none whitespace-nowrap rounded-[var(--radius-pill)] ' +
  'transition-[background,box-shadow,color,border-color] duration-[var(--duration-fast)] ease-[var(--ease-out-premium)] ' +
  'disabled:opacity-45 disabled:cursor-not-allowed overflow-hidden'

const variants: Record<Variant, string> = {
  primary:
    'text-abyss bg-[linear-gradient(110deg,var(--color-champagne-300),var(--color-champagne-400)_45%,var(--color-champagne-200)_55%,var(--color-champagne-400))] ' +
    'bg-[length:220%_100%] hover:bg-[position:100%_0] shadow-[var(--shadow-glow-champagne)] hover:shadow-[0_0_0_1px_rgb(205_176_122/0.6),0_16px_50px_-12px_rgb(205_176_122/0.7)]',
  secondary:
    'text-ivory bg-ink-3/70 border border-line-strong hover:border-steel-400/60 hover:bg-ink-3 hover:shadow-[var(--shadow-glow-steel)]',
  ghost: 'text-mist hover:text-ivory hover:bg-white/5',
  danger: 'text-ivory bg-danger/15 border border-danger/40 hover:bg-danger/25',
}

const sizes: Record<Size, string> = {
  sm: 'h-9 px-4 text-sm',
  md: 'h-11 px-5 text-[0.95rem]',
  lg: 'h-14 px-8 text-base',
}

export function buttonClass(variant: Variant = 'secondary', size: Size = 'md', extra = '') {
  return `${base} ${variants[variant]} ${sizes[size]} ${extra}`
}

/** Micro-interaction partagée : petit ressort à l'appui, étincelle au clic. */
function usePress() {
  const ref = useRef<HTMLElement | null>(null)
  const down = () => ref.current && gsap.to(ref.current, { scale: 0.96, duration: d('instant'), ease: ease.out })
  const up = () => ref.current && gsap.to(ref.current, { scale: 1, duration: d('base'), ease: ease.spring })
  const spark = (e: React.MouseEvent) => {
    const el = ref.current
    if (!el || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const rect = el.getBoundingClientRect()
    const dot = document.createElement('span')
    dot.setAttribute('aria-hidden', 'true')
    dot.style.cssText = `position:absolute;left:${e.clientX - rect.left}px;top:${e.clientY - rect.top}px;width:8px;height:8px;margin:-4px;border-radius:999px;pointer-events:none;background:radial-gradient(circle,#fff,rgba(255,255,255,0));`
    el.appendChild(dot)
    gsap.to(dot, { scale: 14, opacity: 0, duration: d('slow'), ease: ease.out, onComplete: () => dot.remove() })
  }
  return { ref, handlers: { onPointerDown: down, onPointerUp: up, onPointerLeave: up, onClick: spark } }
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  icon?: ReactNode
  loading?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', icon, loading, className = '', children, onClick, disabled, ...rest },
  forwarded,
) {
  const { ref, handlers } = usePress()
  return (
    <button
      ref={(node) => {
        ref.current = node
        if (typeof forwarded === 'function') forwarded(node)
        else if (forwarded) forwarded.current = node
      }}
      className={buttonClass(variant, size, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
      onPointerDown={handlers.onPointerDown}
      onPointerUp={handlers.onPointerUp}
      onPointerLeave={handlers.onPointerLeave}
      onClick={(e) => {
        handlers.onClick(e)
        onClick?.(e)
      }}
    >
      {loading ? <span className="size-4 rounded-full border-2 border-current border-r-transparent animate-spin" aria-hidden="true" /> : icon}
      {children}
    </button>
  )
})

export function ButtonLink({
  variant = 'secondary', size = 'md', icon, className = '', children, ...rest
}: LinkProps & { variant?: Variant; size?: Size; icon?: ReactNode }) {
  const { ref, handlers } = usePress()
  return (
    <Link ref={(n) => { ref.current = n }} className={buttonClass(variant, size, className)} {...handlers} {...rest}>
      {icon}
      {children}
    </Link>
  )
}

export function IconButton({ label, children, className = '', ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  const { ref, handlers } = usePress()
  return (
    <button
      ref={(n) => { ref.current = n }}
      aria-label={label}
      title={label}
      className={`inline-grid place-items-center size-10 rounded-full text-mist hover:text-ivory hover:bg-white/8 transition-colors duration-[var(--duration-fast)] ${className}`}
      {...handlers}
      {...rest}
    >
      {children}
    </button>
  )
}
