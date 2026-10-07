import { useState } from 'react'
import { Send } from 'lucide-react'
import { texts } from '../content/texts'
import { api, ApiError } from '../lib/api'
import { Button } from './ui/Button'
import { Dialog } from './ui/Dialog'
import { Field, TextArea, TextInput } from './ui/Field'
import { useToast } from './ui/Toast'

export function SuggestionDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const toast = useToast()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [urgency, setUrgency] = useState('normal')
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)

  const send = async () => {
    if (title.trim().length < 3) {
      setError('Une phrase de trois lettres minimum, s\'il vous plaît. Même « RFP » compte.')
      return
    }
    setSending(true)
    try {
      await api.suggest({ title, description, urgency })
      toast('magic', texts.suggest.sent)
      setTitle('')
      setDescription('')
      setUrgency('normal')
      setError(null)
      onClose()
    } catch (e) {
      setError(e instanceof ApiError ? `${e.message} ${e.hint}` : texts.errors.generic)
    } finally {
      setSending(false)
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={texts.suggest.title}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>{texts.common.cancel}</Button>
          <Button variant="primary" onClick={send} loading={sending} icon={<Send size={16} />}>{texts.suggest.send}</Button>
        </>
      }
    >
      <div className="flex flex-col gap-5">
        <p className="text-mist">{texts.suggest.body}</p>
        <Field label={texts.suggest.titleLabel} required error={error}>
          {({ id, describedBy, invalid }) => (
            <TextInput id={id} aria-describedby={describedBy} aria-invalid={invalid} value={title} maxLength={140}
              placeholder={texts.suggest.titlePlaceholder} onChange={(e) => setTitle(e.target.value)} />
          )}
        </Field>
        <Field label={texts.suggest.descriptionLabel}>
          {({ id }) => <TextArea id={id} value={description} placeholder={texts.suggest.descriptionPlaceholder} onChange={(e) => setDescription(e.target.value)} />}
        </Field>
        <fieldset>
          <legend className="mb-2 text-sm font-medium text-mist">{texts.suggest.urgency}</legend>
          <div className="flex flex-wrap gap-2">
            {Object.entries(texts.suggest.urgencies).map(([value, label]) => (
              <label key={value} className={`cursor-pointer rounded-full border px-4 py-2 text-sm transition-colors has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-sage-400 ${
                urgency === value ? 'border-champagne-400 bg-champagne-400/15 text-champagne-200' : 'border-line-strong text-mist hover:text-ivory'}`}>
                <input type="radio" name="urgency" value={value} checked={urgency === value} onChange={() => setUrgency(value)} className="sr-only" />
                {label}
              </label>
            ))}
          </div>
        </fieldset>
      </div>
    </Dialog>
  )
}
