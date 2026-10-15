/**
 * Modifications en masse : prévisualisation (aucune écriture), puis écriture avec le mot de passe ; « Passer en force »
 * écrit aussi les contenus en alerte. Journal des lots, chacun annulable (même mot de passe).
 */
import { useState } from 'react'
import { AlertTriangle, Eye, Lock, RotateCcw, ShieldCheck } from 'lucide-react'
import { texts } from '../../content/texts'
import { api, ApiError } from '../../lib/api'
import type { QvidianApplyResult, QvidianJournalEntry, QvidianPlan } from '../../lib/types'
import { Button } from '../ui/Button'
import { Field, Select, Switch, TextInput } from '../ui/Field'
import { useToast } from '../ui/Toast'

const Q = texts.qvidian
const ACTIONS = ['disable', 'enable', 'expire', 'alert', 'clear_alert', 'comment', 'replace_title', 'replace_text'] as const

export function BulkPanel({ ids, writeEnabled, journal, onWritten }: {
  ids: number[]; writeEnabled: boolean; journal: QvidianJournalEntry[]; onWritten: () => void
}) {
  const toast = useToast()
  const [action, setAction] = useState<(typeof ACTIONS)[number]>('disable')
  const [params, setParams] = useState<Record<string, string | boolean>>({})
  const [plan, setPlan] = useState<QvidianPlan | null>(null)
  const [password, setPassword] = useState('')
  const [force, setForce] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<QvidianApplyResult | null>(null)
  const [undoing, setUndoing] = useState<string | null>(null)
  const [undoPassword, setUndoPassword] = useState('')
  const fail = (e: unknown) => toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
  const set = (k: string, v: string | boolean) => { setParams((p) => ({ ...p, [k]: v })); setPlan(null) }

  const preview = async () => {
    setBusy(true)
    setResult(null)
    try { setPlan(await api.qvidian.plan(ids, action, params)) } catch (e) { fail(e) } finally { setBusy(false) }
  }
  const apply = async () => {
    if (!plan) return
    setBusy(true)
    try {
      const r = await api.qvidian.apply(plan.id, password, force)
      setResult(r)
      setPlan(null)
      setPassword('')
      toast(r.failed ? 'error' : 'success', Q.applied(r.written, r.skipped, r.failed))
      onWritten()
    } catch (e) { fail(e) } finally { setBusy(false) }
  }
  const undo = async (batch: string) => {
    setBusy(true)
    try {
      const r = await api.qvidian.undo(batch, undoPassword)
      toast(r.failed ? 'error' : 'success', Q.applied(r.written, r.skipped, r.failed))
      setUndoing(null)
      setUndoPassword('')
      onWritten()
    } catch (e) { fail(e) } finally { setBusy(false) }
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm font-semibold text-fg-2">{Q.bulkLead}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={Q.action}>
          {({ id }) => (
            <Select id={id} value={action} onChange={(e) => { setAction(e.target.value as (typeof ACTIONS)[number]); setParams({}); setPlan(null) }}>
              {ACTIONS.map((a) => <option key={a} value={a}>{Q.actions[a]}</option>)}
            </Select>
          )}
        </Field>
        {action === 'expire' && (
          <Field label={Q.date}>{({ id }) => <TextInput id={id} type="date" value={String(params.date ?? '')} onChange={(e) => set('date', e.target.value)} />}</Field>
        )}
        {(action === 'alert' || action === 'comment') && (
          <Field label={Q.text}>{({ id }) => <TextInput id={id} value={String(params.text ?? '')} onChange={(e) => set('text', e.target.value)} />}</Field>
        )}
        {(action === 'replace_title' || action === 'replace_text') && (
          <>
            <Field label={Q.find}>{({ id }) => <TextInput id={id} value={String(params.find ?? '')} onChange={(e) => set('find', e.target.value)} />}</Field>
            <Field label={Q.replace}>{({ id }) => <TextInput id={id} value={String(params.replace ?? '')} onChange={(e) => set('replace', e.target.value)} />}</Field>
            <Switch checked={!!params.case} onChange={(v) => set('case', v)} label={Q.caseSensitive} />
          </>
        )}
      </div>
      <Button onClick={preview} disabled={ids.length === 0 || busy} loading={busy && !plan} icon={<Eye size={17} />}>{Q.preview} ({ids.length})</Button>

      {plan && (
        <div className="flex flex-col gap-3 rounded-2xl border-2 border-fg bg-card p-3">
          <p className="text-sm font-bold">
            {plan.label} · {plan.items.length} contenu{plan.items.length > 1 ? 's' : ''}
            {plan.unchanged.length > 0 && <span className="text-fg-3"> · {Q.unchanged(plan.unchanged.length)}</span>}
            {plan.warnings > 0 && <span className="text-warning"> · {Q.warnings(plan.warnings)}</span>}
          </p>
          <div className="max-h-80 overflow-auto">
            <table className="w-full text-xs">
              <thead><tr className="text-left"><th className="p-1">#</th><th className="p-1">{Q.before}</th><th className="p-1">{Q.after}</th></tr></thead>
              <tbody>
                {plan.items.map((it) => (
                  <tr key={it.id} className="border-t border-fg/15 align-top">
                    <td className="p-1 font-bold">#{it.id}<span className="block font-semibold text-fg-3">{it.title.slice(0, 40)}</span></td>
                    <td className="p-1 text-fg-2 line-through decoration-bubble-400">{it.before}</td>
                    <td className="p-1 font-semibold">{it.after}
                      {it.warnings.map((w) => <span key={w} className="mt-1 flex items-start gap-1 font-bold text-warning"><AlertTriangle size={12} className="mt-px shrink-0" aria-hidden="true" />{w}</span>)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {writeEnabled ? (
            <div className="flex flex-col gap-2 rounded-xl border-2 border-dashed border-fg/40 p-3">
              <p className="flex items-center gap-1.5 text-sm font-bold"><Lock size={15} aria-hidden="true" />{Q.writeLocked}</p>
              <Field label={Q.writePassword}>
                {({ id }) => <TextInput id={id} type="password" autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)} />}
              </Field>
              {plan.warnings > 0 && <Switch checked={force} onChange={setForce} label={Q.force} />}
              <Button variant="danger" onClick={apply} disabled={!password || busy || plan.items.length === 0} loading={busy} icon={<ShieldCheck size={17} />}>
                {Q.apply(plan.items.length)}
              </Button>
            </div>
          ) : <p className="text-sm font-bold text-fg-3">{Q.writeOff}</p>}
        </div>
      )}

      {result && (
        <ul className="flex flex-col gap-1 text-xs">
          {result.results.filter((r) => !r.ok).map((r) => (
            <li key={r.id} className="font-semibold"><b>#{r.id}</b> · {r.skipped ? 'laissé de côté' : 'échec'} : {r.error}</li>
          ))}
        </ul>
      )}

      <div>
        <h4 className="text-sm font-bold">{Q.journalTitle}</h4>
        {journal.length === 0 ? <p className="text-xs font-semibold text-fg-3">{Q.noJournal}</p> : (
          <ul className="mt-2 flex flex-col gap-2">
            {journal.slice(0, 10).map((j) => (
              <li key={j.batch} className="rounded-xl border-2 border-fg/20 bg-card p-2 text-xs">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-bold">{j.label}</span>
                  <span className="text-fg-3">{j.at.replace('T', ' ')} · {j.user} · {j.items.filter((i) => i.ok).length} écrit(s){j.force ? ` · ${Q.forced}` : ''}{j.source === 'demo' ? ' · démo' : ''}</span>
                  {!j.undo_of && j.items.some((i) => i.ok) && writeEnabled && (
                    <button onClick={() => setUndoing(undoing === j.batch ? null : j.batch)} className="ml-auto inline-flex items-center gap-1 rounded-full border-2 border-fg/40 px-2 py-0.5 font-bold hover:border-fg">
                      <RotateCcw size={12} aria-hidden="true" />{Q.undo}
                    </button>
                  )}
                </div>
                {undoing === j.batch && (
                  <div className="mt-2 flex flex-wrap items-end gap-2">
                    <Field label={Q.undoTitle}>
                      {({ id }) => <TextInput id={id} type="password" autoComplete="off" value={undoPassword} onChange={(e) => setUndoPassword(e.target.value)} />}
                    </Field>
                    <Button size="sm" variant="danger" onClick={() => undo(j.batch)} disabled={!undoPassword || busy}>{Q.undo}</Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
