import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react'

export const inputClass =
  'w-full h-11 rounded-xl bg-abyss/60 border border-line-strong px-3.5 text-parchment placeholder:text-haze ' +
  'transition-[border-color,box-shadow,background] duration-[var(--duration-fast)] ease-[var(--ease-out-magic)] ' +
  'hover:border-violet-400/50 focus:outline-none focus-visible:outline-none focus:border-arcane-400 ' +
  'focus:shadow-[0_0_0_3px_rgb(94_234_212/0.18),0_0_24px_-6px_rgb(94_234_212/0.45)] focus:bg-abyss/80 ' +
  'aria-[invalid=true]:border-danger/70 disabled:opacity-50'

interface FieldProps {
  label: string
  hint?: ReactNode
  error?: string | null
  required?: boolean
  badge?: ReactNode
  children: (props: { id: string; describedBy?: string; invalid: boolean }) => ReactNode
}

export function Field({ label, hint, error, required, badge, children }: FieldProps) {
  const id = useId()
  const hintId = hint ? `${id}-hint` : undefined
  const errorId = error ? `${id}-error` : undefined
  const describedBy = [hintId, errorId].filter(Boolean).join(' ') || undefined
  return (
    <div className="group flex flex-col gap-1.5">
      <label htmlFor={id} className="flex items-center gap-2 text-sm font-medium text-mist group-focus-within:text-parchment transition-colors">
        {label}
        {required && <span className="text-gold-400" aria-hidden="true">*</span>}
        {badge}
      </label>
      {children({ id, describedBy, invalid: !!error })}
      {hint && <p id={hintId} className="text-xs text-haze">{hint}</p>}
      {error && <p id={errorId} role="alert" className="text-xs text-danger">{error}</p>}
    </div>
  )
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${inputClass} ${props.className ?? ''}`} />
}

export function Select({ children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="relative">
      <select {...props} className={`${inputClass} appearance-none pr-10 ${props.className ?? ''}`}>
        {children}
      </select>
      <span aria-hidden="true" className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-haze">▾</span>
    </div>
  )
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={`${inputClass} h-auto min-h-28 py-3 resize-y ${props.className ?? ''}`} />
}

export function Switch({ checked, onChange, label, hint, id }: { checked: boolean; onChange: (v: boolean) => void; label: string; hint?: string; id?: string }) {
  const autoId = useId()
  const switchId = id ?? autoId
  return (
    <div className="flex items-start gap-3">
      <button
        id={switchId}
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative mt-0.5 h-6 w-11 shrink-0 rounded-full border transition-colors duration-[var(--duration-fast)] ${
          checked ? 'bg-arcane-400/30 border-arcane-400/70' : 'bg-abyss/60 border-line-strong'
        }`}
      >
        <span
          aria-hidden="true"
          className={`absolute top-0.5 size-[1.15rem] rounded-full transition-[transform,background] duration-[var(--duration-base)] ease-[var(--ease-spring)] ${
            checked ? 'translate-x-[1.3rem] bg-arcane-300 shadow-[0_0_12px_rgb(94_234_212/0.8)]' : 'translate-x-0.5 bg-mist'
          }`}
        />
      </button>
      <label htmlFor={switchId} className="text-sm text-mist cursor-pointer">
        <span className="text-parchment font-medium">{label}</span>
        {hint && <span className="block text-xs text-haze mt-0.5">{hint}</span>}
      </label>
    </div>
  )
}
