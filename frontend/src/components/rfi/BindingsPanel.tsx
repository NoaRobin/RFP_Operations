/** Liaisons apprises : quelle colonne Fabric correspondait à chaque question des anciens RFI ; l'équipe valide ou rejette. */
import { useEffect, useState } from 'react'
import { Check, Link2, Sparkles, X } from 'lucide-react'
import { texts } from '../../content/texts'
import { api, ApiError } from '../../lib/api'
import type { Binding } from '../../lib/types'
import { useToast } from '../ui/Toast'

const STYLE: Record<string, string> = { candidate: 'bg-sun-400', validated: 'bg-mint-400', rejected: 'bg-card-2 line-through', ambiguous: 'bg-card-2', weak: 'bg-card-2' }

export function BindingsPanel() {
  const toast = useToast()
  const [items, setItems] = useState<Binding[]>([])
  const [busy, setBusy] = useState(false)
  const T = texts.bindings
  const load = () => api.rfi.bindings().then(setItems).catch(() => setItems([]))
  useEffect(() => { void load() }, [])

  const build = async () => {
    setBusy(true)
    try {
      const r = await api.rfi.buildBindings()
      toast('success', `${r.total} liaisons`, Object.entries(r.by_status).map(([k, v]) => `${v} ${T.status[k] ?? k}`).join(' · '))
      await load()
    } catch (e) {
      toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
    } finally { setBusy(false) }
  }
  const set = async (b: Binding, status: string) => {
    const updated = await api.rfi.bindingStatus(b.id, status)
    setItems((xs) => xs.map((x) => (x.id === b.id ? updated : x)))
  }
  return (
    <div className="rounded-2xl border-2 border-fg bg-card p-4">
      <p className="flex items-center gap-2 font-display text-lg font-semibold"><Link2 size={18} aria-hidden="true" />{T.title}</p>
      <p className="mt-1 text-sm font-semibold text-fg-2">{T.lead}</p>
      <button onClick={build} disabled={busy} className="mt-3 inline-flex items-center gap-1.5 rounded-full border-2 border-fg bg-sun-400 px-3.5 py-1.5 text-sm font-bold shadow-[2px_2px_0_0_var(--color-fg)]">
        <Sparkles size={15} aria-hidden="true" />{busy ? T.building : T.build}
      </button>
      {items.length === 0 ? <p className="mt-2 text-sm font-semibold text-fg-3">{T.empty}</p> : (
        <ul className="mt-3 flex max-h-80 flex-col gap-1.5 overflow-y-auto pr-1">
          {items.map((b) => (
            <li key={b.id} className="rounded-xl border-2 border-fg/20 px-2.5 py-1.5 text-xs font-semibold">
              <p className="flex flex-wrap items-center gap-1.5">
                <span className={`rounded-full border-2 border-fg px-2 py-px font-bold ${STYLE[b.status]}`}>{T.status[b.status] ?? b.status}</span>
                <span className="font-bold">{T.support(b.support, b.compared)}</span>
                <span className="ml-auto flex gap-1">
                  {b.status !== 'validated' && b.status !== 'ambiguous' && b.status !== 'weak' && <button onClick={() => set(b, 'validated')} aria-label={T.validate} className="rounded-full border-2 border-fg p-0.5"><Check size={12} /></button>}
                  {b.status !== 'rejected' && <button onClick={() => set(b, 'rejected')} aria-label={T.reject} className="rounded-full border-2 border-fg/40 p-0.5"><X size={12} /></button>}
                </span>
              </p>
              <p className="mt-0.5 text-fg">{b.question}</p>
              <p className="text-fg-3">→ {b.label} <code className="text-[0.65rem]">{b.target}</code></p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
