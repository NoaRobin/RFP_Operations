/** Compléteur RFI : questions sans réponse → équipe à contacter (inventaire des mails) et mail type prêt à copier. */
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Copy, Mail, Users } from 'lucide-react'
import { texts } from '../../content/texts'
import { api } from '../../lib/api'
import type { AskPlan, RfiAnalysis } from '../../lib/types'
import { copyText } from '../qvidian/Bits'
import { Button } from '../ui/Button'
import { TextInput } from '../ui/Field'
import { useToast } from '../ui/Toast'

const T = texts.contacts

export function AskPanel({ analysis, client }: { analysis: RfiAnalysis; client: string }) {
  const toast = useToast()
  const [plan, setPlan] = useState<AskPlan | null>(null)
  const [who, setWho] = useState(client)
  const [deadline, setDeadline] = useState('')
  const missing = useMemo(
    () => analysis.questions.filter((q) => !q.answer && q.status !== 'existing' && q.status !== 'skipped').map((q) => q.question),
    [analysis],
  )
  useEffect(() => {
    if (!missing.length) { setPlan(null); return }
    const t = window.setTimeout(() => { api.contacts.ask(missing, who, '', deadline).then(setPlan).catch(() => setPlan(null)) }, 300)
    return () => window.clearTimeout(t)
  }, [missing, who, deadline])
  if (!missing.length) return null
  return (
    <aside className="rounded-[var(--radius-card)] border-[2.5px] border-fg bg-[#ffff00]/25 p-5" aria-label={T.askTitle}>
      <h3 className="flex items-center gap-2 text-lg"><Users size={18} aria-hidden="true" />{T.askTitle} ({missing.length})</h3>
      <p className="mt-1 text-xs font-semibold text-fg-2">{T.askLead}</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-xs font-bold">{T.askClient}<TextInput value={who} onChange={(e) => setWho(e.target.value)} /></label>
        <label className="flex flex-col gap-1 text-xs font-bold">{T.askDeadline}<TextInput value={deadline} placeholder="15/11" onChange={(e) => setDeadline(e.target.value)} /></label>
      </div>
      {plan && !plan.built_at && <p className="mt-3 text-sm font-semibold">{T.askNoInventory} <Link to="/qui-contacter" className="underline">{T.title}</Link></p>}
      <ul className="mt-3 flex flex-col gap-3">
        {(plan?.teams ?? []).map((t) => (
          <li key={t.team} className="rounded-2xl border-2 border-fg bg-card p-4">
            <p className="font-display font-semibold">{t.team} · {t.questions.length} question{t.questions.length > 1 ? 's' : ''}</p>
            <p className="text-xs font-semibold text-fg-2">{T.askTo} : {t.people.join(', ') || '—'}</p>
            <textarea readOnly value={t.mail} rows={Math.min(14, 6 + t.questions.length)} aria-label={`Mail pour ${t.team}`}
              className="mt-2 w-full rounded-xl border-2 border-fg/30 bg-card-2 p-2 text-sm" />
            <Button size="sm" className="mt-2" icon={<Copy size={14} />}
              onClick={async () => { const ok = await copyText(t.mail); toast(ok ? 'success' : 'error', ok ? T.askCopied : texts.qvidian.copyFailed) }}>{T.askCopy}</Button>
            <a className="ml-2 inline-flex items-center gap-1 text-sm font-bold underline" href={`mailto:${encodeURIComponent(t.to)}?body=${encodeURIComponent(t.mail)}`}>
              <Mail size={14} aria-hidden="true" />Outlook
            </a>
          </li>
        ))}
      </ul>
      {!!plan?.unknown.length && (
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer font-bold">{T.askUnknown} ({plan.unknown.length})</summary>
          <ul className="mt-1 list-disc pl-5 text-xs font-semibold">{plan.unknown.map((q) => <li key={q}>{q}</li>)}</ul>
        </details>
      )}
    </aside>
  )
}
