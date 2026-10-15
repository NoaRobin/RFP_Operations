import { useEffect, useState } from 'react'
import { texts } from '../content/texts'
import { setLowPowerPref, setUserName, useLowPowerPref, useUserName } from '../lib/storage'
import { Button } from './ui/Button'
import { Dialog } from './ui/Dialog'
import { Field, Switch, TextInput } from './ui/Field'

export function UserDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const current = useUserName()
  const lowPower = useLowPowerPref()
  const [name, setName] = useState(current)
  useEffect(() => {
    if (open) setName(current)
  }, [open, current])

  const save = () => {
    setUserName(name)
    onClose()
  }
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={texts.user.promptTitle}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>{texts.common.cancel}</Button>
          <Button variant="primary" onClick={save}>{texts.user.promptSave}</Button>
        </>
      }
    >
      <form
        className="flex flex-col gap-5"
        onSubmit={(e) => {
          e.preventDefault()
          save()
        }}
      >
        <p className="text-fg-2">{texts.user.promptBody}</p>
        <Field label={texts.user.promptLabel}>
          {({ id }) => <TextInput id={id} value={name} maxLength={60} autoFocus onChange={(e) => setName(e.target.value)} placeholder="Viviane L." />}
        </Field>
        <Switch checked={lowPower} onChange={setLowPowerPref} label={texts.user.lowPower} hint={texts.user.lowPowerHint} />
      </form>
    </Dialog>
  )
}
