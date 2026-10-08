import { useState } from 'react'
import { CalendarClock } from 'lucide-react'
import { texts } from '../content/texts'
import { api, ApiError } from '../lib/api'
import { Button } from './ui/Button'
import { Dialog } from './ui/Dialog'
import { Field, Select, TextInput } from './ui/Field'
import { useToast } from './ui/Toast'

type Frequency = 'on_demand' | 'daily' | 'weekly' | 'monthly'

/** Planification en langage humain : à la demande, quotidien, hebdo, mensuel. */
export function ScheduleDialog({
  open, onClose, targetType, targetId, label, params = {},
}: { open: boolean; onClose: () => void; targetType: 'automation' | 'recipe'; targetId: string; label: string; params?: Record<string, unknown> }) {
  const toast = useToast()
  const [frequency, setFrequency] = useState<Frequency>('weekly')
  const [time, setTime] = useState('08:00')
  const [weekday, setWeekday] = useState(0)
  const [day, setDay] = useState(1)
  const [error, setError] = useState<ApiError | null>(null)
  const [saving, setSaving] = useState(false)

  const save = async () => {
    if (frequency === 'on_demand') {
      onClose()
      return
    }
    const [hour, minute] = time.split(':').map(Number)
    setSaving(true)
    setError(null)
    try {
      await api.createSchedule({
        target_type: targetType, target_id: targetId, label, frequency, hour, minute,
        params, weekday: frequency === 'weekly' ? weekday : null, day_of_month: frequency === 'monthly' ? day : null,
      })
      toast('success', texts.schedule.saved)
      onClose()
    } catch (e) {
      setError(e as ApiError)
    } finally {
      setSaving(false)
    }
  }

  const options: [Frequency, string][] = [
    ['on_demand', texts.schedule.onDemand], ['daily', texts.schedule.daily],
    ['weekly', texts.schedule.weekly], ['monthly', texts.schedule.monthly],
  ]

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={`${texts.schedule.title} · ${label}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>{texts.common.cancel}</Button>
          <Button variant="primary" onClick={save} loading={saving} icon={<CalendarClock size={16} />}>
            {frequency === 'on_demand' ? texts.common.close : texts.schedule.save}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-5">
        <fieldset>
          <legend className="mb-2 text-sm font-medium text-fg-2">{texts.schedule.frequency}</legend>
          <div className="grid grid-cols-2 gap-2">
            {options.map(([value, text]) => (
              <label key={value} className={`cursor-pointer rounded-xl border px-4 py-3 text-sm transition-all duration-[var(--duration-fast)] has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-mint-400 ${
                frequency === value ? 'border-sun-400 bg-sun-400/12 text-sun-200 shadow-[var(--shadow-glow-sun)]' : 'border-line-strong text-fg-2 hover:border-magic-400/50'}`}>
                <input type="radio" name="frequency" value={value} checked={frequency === value} onChange={() => setFrequency(value)} className="sr-only" />
                {text}
              </label>
            ))}
          </div>
        </fieldset>
        {frequency === 'on_demand' ? (
          <p className="text-fg-2">{texts.schedule.onDemandHint}</p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {frequency === 'weekly' && (
              <Field label={texts.schedule.weekday}>
                {({ id }) => (
                  <Select id={id} value={weekday} onChange={(e) => setWeekday(Number(e.target.value))}>
                    {texts.schedule.weekdays.map((w, i) => <option key={w} value={i}>{w}</option>)}
                  </Select>
                )}
              </Field>
            )}
            {frequency === 'monthly' && (
              <Field label={texts.schedule.dayOfMonth}>
                {({ id }) => (
                  <Select id={id} value={day} onChange={(e) => setDay(Number(e.target.value))}>
                    {Array.from({ length: 28 }, (_, i) => <option key={i + 1} value={i + 1}>{i + 1}</option>)}
                    <option value={31}>{texts.schedule.lastDay}</option>
                  </Select>
                )}
              </Field>
            )}
            <Field label={texts.schedule.time}>
              {({ id }) => <TextInput id={id} type="time" value={time} onChange={(e) => setTime(e.target.value)} />}
            </Field>
          </div>
        )}
        {frequency !== 'on_demand' && <p className="text-xs text-fg-3">{texts.schedule.paramsNote}</p>}
        {error && <p role="alert" className="text-sm text-danger">{error.message} {error.hint}</p>}
      </div>
    </Dialog>
  )
}
