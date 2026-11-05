/**
 * Atelier de modification : 1. sélection, 2. action, 3. prévisualisation avant / après (aucune écriture),
 * 4. validation avec le mot de passe d'équipe (QVIDIAN_WRITE_PASSWORD du .env) ; « passer en force » écrit aussi les
 * contenus en alerte. Chaque lot est journalisé et annulable (même mot de passe).
 */
import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  AlertTriangle, Ban, BellOff, BellRing, CalendarClock, Eye, FolderInput, KeyRound, Lock, MessageSquare, PenLine, Power, Replace, ShieldCheck, Tags, Type, X,
} from 'lucide-react'
import { Button } from '../../../components/ui/Button'
import { Field, Select, Switch, TextArea, TextInput } from '../../../components/ui/Field'
import { useToast } from '../../../components/ui/Toast'
import { texts } from '../../../content/texts'
import { api } from '../../../lib/api'
import type { QvidianApplyResult, QvidianFolder, QvidianPlan } from '../../../lib/types'
import { useQvidian } from '../context'

const Q = texts.qvidian
type Action = 'disable' | 'enable' | 'expire' | 'alert' | 'clear_alert' | 'comment' | 'replace_title' | 'replace_text' | 'set_text' | 'move' | 'add_terms'
const GROUPS: { key: string; actions: { id: Action; icon: typeof Ban }[] }[] = [
  { key: 'statut', actions: [{ id: 'disable', icon: Ban }, { id: 'enable', icon: Power }, { id: 'expire', icon: CalendarClock },
    { id: 'alert', icon: BellRing }, { id: 'clear_alert', icon: BellOff }] },
  { key: 'texte', actions: [{ id: 'set_text', icon: PenLine }, { id: 'replace_text', icon: Replace }, { id: 'replace_title', icon: Type },
    { id: 'comment', icon: MessageSquare }] },
  { key: 'classement', actions: [{ id: 'move', icon: FolderInput }, { id: 'add_terms', icon: Tags }] },
]

function Step({ n, title, done, children }: { n: number; title: string; done?: boolean; children: React.ReactNode }) {
  return (
    <section data-enter className="rounded-[var(--radius-card)] border-[2.5px] border-fg bg-card p-5">
      <h2 className="flex items-center gap-3 text-xl">
        <span className={`grid size-8 place-items-center rounded-full border-2 border-fg text-sm font-bold ${done ? 'bg-mint-400' : 'bg-sun-400'}`}>{n}</span>{title}
      </h2>
      <div className="mt-4">{children}</div>
    </section>
  )
}

export function EditView() {
  const toast = useToast()
  const { audit, status, journal, selected, toggle, clear, reload, fail } = useQvidian()
  const [params] = useSearchParams()
  const [action, setAction] = useState<Action>((params.get('action') as Action) || 'disable')
  const [values, setValues] = useState<Record<string, string | boolean>>({})
  const [plan, setPlan] = useState<QvidianPlan | null>(null)
  const [password, setPassword] = useState('')
  const [force, setForce] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<QvidianApplyResult | null>(null)
  const [folders, setFolders] = useState<QvidianFolder[]>([])
  const ids = useMemo(() => [...selected], [selected])
  const byId = useMemo(() => new Map((audit?.items ?? []).map((i) => [i.id, i])), [audit])
  useEffect(() => { api.qvidian.folders().then(setFolders).catch(() => setFolders([])) }, [])
  useEffect(() => { setPlan(null); setResult(null) }, [action, ids.length])
  // Réécriture : le texte actuel du contenu sert de point de départ
  useEffect(() => {
    if (action === 'set_text' && ids.length === 1 && values.text === undefined) setValues((v) => ({ ...v, text: byId.get(ids[0])?.text ?? '' }))
  }, [action, ids, byId, values.text])
  const set = (k: string, v: string | boolean) => { setValues((p) => ({ ...p, [k]: v })); setPlan(null) }
  const preview = async () => {
    setBusy(true)
    setResult(null)
    const p: Record<string, unknown> = { ...values }
    if (action === 'move') p.folder_label = folders.find((f) => String(f.id) === String(values.folder_id))?.path
    try { setPlan(await api.qvidian.plan(ids, action, p)) } catch (e) { fail(e) } finally { setBusy(false) }
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
      void reload()
    } catch (e) { fail(e) } finally { setBusy(false) }
  }
  const single = action === 'set_text'
  return (
    <div className="flex flex-col gap-5">
      <header data-enter>
        <h1 className="text-2xl font-semibold">{Q.editTitle}</h1>
        <p className="mt-2 max-w-3xl text-sm font-semibold text-fg-2">{Q.editLead}</p>
        {!status?.write_enabled && <p className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-bubble-400/30 px-3 py-1 text-sm font-bold"><Lock size={14} aria-hidden="true" />{Q.writeOff}</p>}
      </header>

      <Step n={1} title={`${Q.stepPick} (${ids.length})`} done={ids.length > 0}>
        {ids.length === 0 ? (
          <p className="text-sm font-semibold text-fg-2">{Q.emptySelection} <Link to="/qvidian/recherche" className="font-bold underline">{Q.nav.recherche}</Link> · <Link to="/qvidian/bibliotheque" className="font-bold underline">{Q.nav.bibliotheque}</Link></p>
        ) : (
          <>
            <ul className="flex max-h-56 flex-col gap-1 overflow-y-auto" data-lenis-prevent>
              {ids.map((id) => (
                <li key={id} className="flex items-center gap-2 rounded-lg px-2 py-1 text-sm hover:bg-card-2">
                  <Link to={`/qvidian/contenu/${id}`} className="min-w-0 flex-1 truncate font-semibold hover:underline">#{id} · {byId.get(id)?.title ?? '…'}</Link>
                  <span className="hidden truncate text-xs text-fg-3 md:inline">{byId.get(id)?.folder_path}</span>
                  <button onClick={() => toggle(id, false)} aria-label={`${Q.remove} #${id}`} className="rounded-full p-1 hover:bg-card-3"><X size={13} /></button>
                </li>
              ))}
            </ul>
            <button onClick={clear} className="mt-2 text-xs font-bold underline">{Q.unselect}</button>
          </>
        )}
      </Step>

      <Step n={2} title={Q.stepAction} done={!!plan}>
        <div className="grid gap-4 lg:grid-cols-3">
          {GROUPS.map((g) => (
            <fieldset key={g.key} className="flex flex-col gap-2">
              <legend className="mb-1 text-[0.7rem] font-bold uppercase tracking-widest text-fg-3">{Q.actionGroups[g.key]}</legend>
              {g.actions.map(({ id, icon: Icon }) => (
                <button key={id} onClick={() => { setAction(id); setValues({}) }} aria-pressed={action === id}
                  className={`flex items-start gap-3 rounded-2xl border-2 p-3 text-left transition-shadow ${action === id ? 'border-fg bg-sun-400/40 shadow-[3px_3px_0_0_var(--color-fg)]' : 'border-fg/25 hover:border-fg'}`}>
                  <Icon size={18} className="mt-0.5 shrink-0" aria-hidden="true" />
                  <span><span className="block text-sm font-bold">{Q.actions[id]}</span><span className="block text-xs font-semibold text-fg-2">{Q.actionHelp[id]}</span></span>
                </button>
              ))}
            </fieldset>
          ))}
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {action === 'expire' && <Field label={Q.date}>{({ id }) => <TextInput id={id} type="date" value={String(values.date ?? '')} onChange={(e) => set('date', e.target.value)} />}</Field>}
          {(action === 'alert' || action === 'comment') && <Field label={Q.text}>{({ id }) => <TextInput id={id} value={String(values.text ?? '')} onChange={(e) => set('text', e.target.value)} />}</Field>}
          {(action === 'replace_title' || action === 'replace_text') && (
            <>
              <Field label={Q.find}>{({ id }) => <TextInput id={id} value={String(values.find ?? '')} onChange={(e) => set('find', e.target.value)} />}</Field>
              <Field label={Q.replace}>{({ id }) => <TextInput id={id} value={String(values.replace ?? '')} onChange={(e) => set('replace', e.target.value)} />}</Field>
              <Switch checked={!!values.case} onChange={(v) => set('case', v)} label={Q.caseSensitive} />
            </>
          )}
          {action === 'move' && (
            <Field label={Q.folderTarget}>
              {({ id }) => (
                <Select id={id} value={String(values.folder_id ?? '')} onChange={(e) => set('folder_id', e.target.value)}>
                  <option value="">—</option>
                  {folders.filter((f) => f.path).map((f) => <option key={f.id} value={f.id}>{f.path}</option>)}
                </Select>
              )}
            </Field>
          )}
          {action === 'add_terms' && <Field label={Q.terms}>{({ id }) => <TextInput id={id} value={String(values.text ?? '')} onChange={(e) => set('text', e.target.value)} placeholder="UNPRI, stewardship, vote" />}</Field>}
          {single && (
            <div className="md:col-span-2">
              <Field label={Q.newText} hint={ids.length !== 1 ? 'Cochez un seul contenu pour le réécrire.' : undefined}>
                {({ id, describedBy }) => <TextArea id={id} aria-describedby={describedBy} rows={9} value={String(values.text ?? '')} onChange={(e) => set('text', e.target.value)} />}
              </Field>
            </div>
          )}
        </div>
        <div className="mt-4">
          <Button onClick={preview} disabled={ids.length === 0 || busy || (single && ids.length !== 1)} loading={busy && !plan} icon={<Eye size={17} />}>{Q.preview} ({ids.length})</Button>
        </div>
      </Step>

      {plan && (
        <Step n={3} title={Q.stepPreview} done>
          <p className="text-sm font-bold">
            {plan.label} · {plan.items.length} contenu{plan.items.length > 1 ? 's' : ''}
            {plan.unchanged.length > 0 && <span className="text-fg-3"> · {Q.unchanged(plan.unchanged.length)}</span>}
            {plan.warnings > 0 && <span className="text-warning"> · {Q.warnings(plan.warnings)}</span>}
          </p>
          <div className="mt-3 max-h-[28rem] overflow-auto" data-lenis-prevent>
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs uppercase tracking-wider text-fg-3"><th className="p-2">#</th><th className="p-2">{Q.before}</th><th className="p-2">{Q.after}</th></tr></thead>
              <tbody>
                {plan.items.map((it) => (
                  <tr key={it.id} className="border-t-2 border-fg/10 align-top">
                    <td className="p-2 font-bold">#{it.id}<span className="block max-w-[12rem] truncate text-xs font-semibold text-fg-3">{it.title}</span></td>
                    <td className="whitespace-pre-line p-2 text-fg-2 line-through decoration-bubble-400 decoration-2">{it.before}</td>
                    <td className="whitespace-pre-line p-2 font-semibold">{it.after}
                      {it.warnings.map((w) => <span key={w} className="mt-1 flex items-start gap-1 text-xs font-bold text-warning"><AlertTriangle size={12} className="mt-px shrink-0" aria-hidden="true" />{w}</span>)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Step>
      )}

      {plan && (
        <Step n={4} title={Q.stepWrite}>
          {status?.write_enabled ? (
            <form className="flex max-w-xl flex-col gap-3" onSubmit={(e) => { e.preventDefault(); void apply() }}>
              <p className="flex items-center gap-1.5 text-sm font-bold"><KeyRound size={15} aria-hidden="true" />{Q.writeLocked}</p>
              <Field label={Q.teamPassword} hint={Q.teamPasswordHint}>
                {({ id, describedBy }) => <TextInput id={id} aria-describedby={describedBy} type="password" autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)} />}
              </Field>
              {plan.warnings > 0 && <Switch checked={force} onChange={setForce} label={Q.force} />}
              <Button type="submit" variant="danger" disabled={!password || busy || plan.items.length === 0} loading={busy} icon={<ShieldCheck size={17} />}>{Q.apply(plan.items.length)}</Button>
            </form>
          ) : <p className="text-sm font-bold text-fg-3">{Q.writeOff}</p>}
        </Step>
      )}

      {result && (
        <section data-enter className="rounded-[var(--radius-card)] border-2 border-fg bg-mint-400/20 p-4" aria-live="polite">
          <p className="font-display text-lg font-semibold">{Q.writeDone} · {Q.applied(result.written, result.skipped, result.failed)}</p>
          <ul className="mt-2 flex flex-col gap-1 text-xs">
            {result.results.filter((r) => !r.ok).map((r) => <li key={r.id} className="font-semibold"><b>#{r.id}</b> · {r.skipped ? 'laissé de côté' : 'échec'} : {r.error}</li>)}
          </ul>
          <Link to="/qvidian/journal" className="mt-2 inline-block text-sm font-bold underline">{Q.journalTitle} ({journal.length})</Link>
        </section>
      )}
    </div>
  )
}
