import { forwardRef, useRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { Link, type LinkProps } from 'react-router-dom'
import { gsap } from '../../motion/gsap'
import { d, ease } from '../../motion/tokens'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md' | 'lg'

const base =
  'relative inline-flex items-center justify-center gap-2 font-display font-semibold select-none whitespace-nowrap rounded-[var(--radius-pill)] ' +
  'border-[2.5px] border-fg transition-[transform,box-shadow,background,color] duration-[var(--duration-fast)] ease-[var(--ease-spring)] ' +
  'hover:-translate-x-0.5 hover:-translate-y-0.5 active:translate-x-0.5 active:translate-y-0.5 ' +
  'disabled:opacity-50 disabled:cursor-not-allowed disabled:translate-x-0 disabled:translate-y-0 overflow-hidden'

// Néo-brutal cartoon : contour d'encre, ombre pleine décalée qui grandit au survol et disparaît à l'appui.
const pop = 'shadow-[3px_3px_0_0_var(--color-fg)] hover:shadow-[5px_5px_0_0_var(--color-fg)] active:shadow-[0_0_0_0_var(--color-fg)]'

const variants: Record<Variant, string> = {
  primary: `text-on-accent bg-sun-400 hover:bg-sun-600 ${pop}`,
  secondary: `text-fg bg-card hover:bg-card-2 ${pop}`,
  ghost: 'text-fg-2 border-transparent hover:text-fg hover:bg-fg/5 hover:border-fg/20 hover:translate-x-0 hover:translate-y-0',
  danger: `text-fg bg-[#ffd6dc] hover:bg-[#ffc2cb] ${pop}`,
}

const sizes: Record<Size, string> = {
  sm: 'h-9 px-4 text-sm',
  md: 'h-11 px-5 text-[0.98rem]',
  lg: 'h-14 px-8 text-lg',
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
      className={`inline-grid place-items-center size-10 rounded-full text-fg-2 hover:text-fg hover:bg-fg/8 transition-colors duration-[var(--duration-fast)] ${className}`}
      {...handlers}
      {...rest}
    >
      {children}
    </button>
  )
}
