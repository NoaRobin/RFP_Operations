import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react'

export const inputClass =
  'w-full h-11 rounded-xl bg-field border-2 border-fg px-3.5 text-fg font-semibold placeholder:font-normal placeholder:text-fg-3 ' +
  'transition-[box-shadow,transform,background] duration-[var(--duration-fast)] ease-[var(--ease-spring)] ' +
  'hover:shadow-[3px_3px_0_0_var(--color-fg)] focus:outline-none focus-visible:outline-none ' +
  'focus:shadow-[4px_4px_0_0_var(--color-magic-500)] focus:bg-[#fffdf7] ' +
  'aria-[invalid=true]:border-danger aria-[invalid=true]:shadow-[3px_3px_0_0_var(--color-danger)] disabled:opacity-50'

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
      <label htmlFor={id} className="flex items-center gap-2 text-sm font-medium text-fg-2 group-focus-within:text-fg transition-colors">
        {label}
        {required && <span className="text-sun-400" aria-hidden="true">*</span>}
        {badge}
      </label>
      {children({ id, describedBy, invalid: !!error })}
      {hint && <p id={hintId} className="text-xs text-fg-3">{hint}</p>}
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
      <span aria-hidden="true" className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-fg-3">▾</span>
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
        className={`relative mt-0.5 h-6 w-11 shrink-0 rounded-full border-2 transition-colors duration-[var(--duration-fast)] ${
          checked ? 'bg-mint-400 border-fg' : 'bg-card border-fg'
        }`}
      >
        <span
          aria-hidden="true"
          className={`absolute left-0 top-[1px] size-[1.1rem] rounded-full transition-[transform,background] duration-[var(--duration-base)] ease-[var(--ease-spring)] ${
            checked ? 'translate-x-[1.2rem] bg-card border-2 border-fg' : 'translate-x-0.5 bg-fg-3'
          }`}
        />
      </button>
      <label htmlFor={switchId} className="text-sm text-fg-2 cursor-pointer">
        <span className="text-fg font-medium">{label}</span>
        {hint && <span className="block text-xs text-fg-3 mt-0.5">{hint}</span>}
      </label>
    </div>
  )
}
