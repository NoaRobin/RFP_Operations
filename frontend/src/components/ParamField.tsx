/** Champ de formulaire généré à partir d'un paramètre du manifest. */
import { useEffect, useState } from 'react'
import { texts } from '../content/texts'
import { api } from '../lib/api'
import type { Option, ParamSpec } from '../lib/types'
import { Field, Select, Switch, TextArea, TextInput } from './ui/Field'
import { Badge } from './ui/StatusPill'

interface Props {
  automationId: string
  spec: ParamSpec
  value: unknown
  error?: string | null
  onChange: (value: unknown) => void
}

function useOptions(automationId: string, spec: ParamSpec) {
  const [options, setOptions] = useState<Option[] | null>(spec.options ?? null)
  const [failed, setFailed] = useState<string | null>(null)
  useEffect(() => {
    if (spec.options || !spec.options_query) return
    let alive = true
    api.options(automationId, spec.name)
      .then((o) => alive && setOptions(o))
      .catch((e) => alive && setFailed(e.message))
    return () => {
      alive = false
    }
  }, [automationId, spec])
  return { options, failed }
}

export function ParamField({ automationId, spec, value, error, onChange }: Props) {
  const needsOptions = spec.type === 'select' || spec.type === 'multiselect'
  const { options, failed } = useOptions(automationId, needsOptions ? spec : { ...spec, options_query: null })
  const badge = <Badge tone="muted" className="!py-0 !text-[0.65rem]">{spec.required ? texts.spell.required : texts.spell.optional}</Badge>

  if (spec.type === 'boolean') {
    return <Switch checked={!!value} onChange={onChange} label={spec.label} hint={spec.help ?? undefined} />
  }

  return (
    <Field label={spec.label} hint={spec.help} error={error ?? failed} required={spec.required} badge={badge}>
      {({ id, describedBy, invalid }) => {
        const common = { id, 'aria-describedby': describedBy, 'aria-invalid': invalid, required: spec.required }
        switch (spec.type) {
          case 'date':
            return <TextInput {...common} type="date" value={String(value ?? '')} onChange={(e) => onChange(e.target.value)} />
          case 'integer':
          case 'number':
            return (
              <TextInput {...common} type="number" inputMode="decimal" step={spec.type === 'integer' ? 1 : 'any'}
                min={spec.min ?? undefined} max={spec.max ?? undefined} value={value === null || value === undefined ? '' : String(value)}
                onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))} />
            )
          case 'text':
            return <TextArea {...common} value={String(value ?? '')} placeholder={spec.placeholder ?? ''} onChange={(e) => onChange(e.target.value)} />
          case 'isin':
            return (
              <TextInput {...common} value={String(value ?? '')} maxLength={12} spellCheck={false} autoComplete="off"
                placeholder={spec.placeholder ?? 'QZ0000000000'} className="font-mono uppercase tracking-wider"
                onChange={(e) => onChange(e.target.value.toUpperCase())} />
            )
          case 'select':
            return (
              <Select {...common} value={value === null || value === undefined ? '' : String(value)} disabled={!options && !failed}
                onChange={(e) => onChange(e.target.value || null)}>
                <option value="">{!options && !failed ? texts.spell.loadingOptions : spec.placeholder ?? texts.spell.selectPlaceholder}</option>
                {options?.map((o) => <option key={String(o.value)} value={String(o.value)}>{o.label}</option>)}
              </Select>
            )
          case 'multiselect': {
            const selected = new Set(Array.isArray(value) ? value.map(String) : [])
            return (
              <div id={id} role="group" aria-describedby={describedBy} className="flex max-h-56 flex-col gap-1 overflow-y-auto rounded-xl border border-line-strong bg-abyss/50 p-2">
                {options?.map((o) => (
                  <label key={String(o.value)} className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-white/5">
                    <input type="checkbox" className="accent-[var(--color-gold-400)]" checked={selected.has(String(o.value))}
                      onChange={(e) => {
                        const next = new Set(selected)
                        if (e.target.checked) next.add(String(o.value))
                        else next.delete(String(o.value))
                        onChange([...next])
                      }} />
                    {o.label}
                  </label>
                )) ?? <span className="p-2 text-sm text-haze">{texts.spell.loadingOptions}</span>}
              </div>
            )
          }
          default:
            return <TextInput {...common} value={String(value ?? '')} placeholder={spec.placeholder ?? ''} onChange={(e) => onChange(e.target.value)} />
        }
      }}
    </Field>
  )
}
