/** Connexion au Lakehouse « façon VS Code » : serveur + identifiant, la fenêtre Microsoft fait le reste. */
import { useEffect, useState } from 'react'
import { Plug, Unplug } from 'lucide-react'
import { texts } from '../content/texts'
import { api, ApiError } from '../lib/api'
import type { FabricStatus } from '../lib/types'
import { Button } from './ui/Button'
import { Dialog } from './ui/Dialog'
import { Field, TextInput } from './ui/Field'
import { useToast } from './ui/Toast'

export function FabricDialog({ open, onClose, status, onChange }: {
  open: boolean; onClose: () => void; status: FabricStatus | null; onChange: (s: FabricStatus) => void
}) {
  const toast = useToast()
  const [server, setServer] = useState('')
  const [database, setDatabase] = useState('LKH_RFPTeam_Bronze')
  const [user, setUser] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  useEffect(() => {
    if (!open) return
    setError(null)
    if (status) {
      setServer(status.server || '')
      setDatabase(status.database || 'LKH_RFPTeam_Bronze')
      setUser(status.user || '')
    }
  }, [open, status])

  const connect = async () => {
    setBusy(true)
    setError(null)
    try {
      const next = await api.fabric.connect({ server, database, user })
      onChange(next)
      toast('success', texts.fabric.success)
      onClose()
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(texts.fabric.failed))
    } finally {
      setBusy(false)
    }
  }

  const disconnect = async () => {
    setBusy(true)
    try {
      onChange(await api.fabric.disconnect())
      onClose()
    } finally {
      setBusy(false)
    }
  }

  const connected = status?.mode === 'fabric'
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={texts.fabric.title}
      footer={
        <>
          {connected && <Button variant="ghost" onClick={disconnect} disabled={busy} icon={<Unplug size={16} />}>{texts.fabric.disconnect}</Button>}
          <Button variant="primary" onClick={connect} loading={busy} disabled={!server.trim() || !user.trim()} icon={<Plug size={16} />}>
            {connected ? texts.fabric.reconnect : texts.fabric.go}
          </Button>
        </>
      }
    >
      <form className="flex flex-col gap-5" onSubmit={(e) => { e.preventDefault(); void connect() }}>
        <p className="text-fg-2">{texts.fabric.body}</p>
        <Field label={texts.fabric.server} hint={texts.fabric.serverHint} required>
          {({ id, describedBy }) => (
            <TextInput id={id} aria-describedby={describedBy} value={server} onChange={(e) => setServer(e.target.value)}
              placeholder={texts.fabric.serverPlaceholder} autoComplete="off" spellCheck={false} autoFocus />
          )}
        </Field>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label={texts.fabric.user} required>
            {({ id }) => <TextInput id={id} type="email" value={user} onChange={(e) => setUser(e.target.value)} placeholder={texts.fabric.userPlaceholder} autoComplete="username" />}
          </Field>
          <Field label={texts.fabric.database}>
            {({ id }) => <TextInput id={id} value={database} onChange={(e) => setDatabase(e.target.value)} spellCheck={false} />}
          </Field>
        </div>
        {busy && <p role="status" className="rounded-xl border-2 border-fg bg-sun-400/30 px-4 py-3 font-semibold">{texts.fabric.waiting}</p>}
        {error && (
          <div role="alert" className="rounded-xl border-2 border-danger bg-[#ffe3e7] px-4 py-3">
            <p className="font-semibold text-danger">{error.message}</p>
            {error.hint && <p className="mt-1 text-sm text-fg-2">{error.hint}</p>}
          </div>
        )}
        <button type="submit" hidden />
      </form>
    </Dialog>
  )
}
