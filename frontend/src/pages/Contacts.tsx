/** Qui contacter : inventaire des questions posées aux autres équipes, lu dans Outlook (mails avec l'équipe RFP en copie). */
import { useEffect, useState } from 'react'
import { Download, Mail, Square, Upload } from 'lucide-react'
import { Button } from '../components/ui/Button'
import { Select, TextInput } from '../components/ui/Field'
import { useToast } from '../components/ui/Toast'
import { texts } from '../content/texts'
import { api, ApiError } from '../lib/api'
import type { ContactGroup, ContactsStatus } from '../lib/types'

const T = texts.contacts

export default function Contacts() {
  const toast = useToast()
  const [st, setSt] = useState<ContactsStatus | null>(null)
  const [months, setMonths] = useState(36)
  const [rows, setRows] = useState<ContactGroup[]>([])
  const [q, setQ] = useState('')
  const [team, setTeam] = useState('')
  const [dd, setDd] = useState('')
  const fail = (e: unknown) => toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
  useEffect(() => { api.contacts.status().then(setSt).catch(fail) }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const t = window.setTimeout(() => { api.contacts.questions(q, team, dd).then(setRows).catch(() => setRows([])) }, 200)
    return () => window.clearTimeout(t)
  }, [q, team, dd, st?.summary.built_at, st?.summary.corrections])
  useEffect(() => {
    if (!st?.state.running) return
    const t = window.setInterval(() => { api.contacts.status().then(setSt).catch(() => undefined) }, 1500)
    return () => window.clearInterval(t)
  }, [st?.state.running])
  const s = st?.summary
  return (
    <div className="mx-auto flex w-[min(100%-2rem,82rem)] flex-col gap-5 pt-10 sm:pt-14">
      <header data-enter>
        <h1 className="flex items-center gap-3 text-[clamp(2rem,4vw,3rem)] font-bold leading-none"><Mail size={30} aria-hidden="true" />{T.title}</h1>
        <p className="mt-2 max-w-3xl text-sm font-semibold text-fg-2">{T.lead(st?.team ?? 'AmeuRFPteam')}</p>
      </header>
      <section data-enter className="flex flex-wrap items-end gap-3 rounded-[var(--radius-card)] border-2 border-fg bg-card p-5">
        <label className="flex flex-col gap-1 text-xs font-bold">{T.months}
          <Select value={months} onChange={(e) => setMonths(Number(e.target.value))}>
            {[6, 12, 24, 36, 60].map((m) => <option key={m} value={m}>{T.monthsOpt(m)}</option>)}
          </Select>
        </label>
        {st?.state.running
          ? <Button onClick={async () => setSt(await api.contacts.stop())} icon={<Square size={14} />}>{T.stop}</Button>
          : <Button variant="primary" disabled={!st?.outlook} onClick={async () => { try { setSt(await api.contacts.scan(months)) } catch (e) { fail(e) } }} icon={<Mail size={15} />}>{T.scan}</Button>}
        <a href={api.contacts.exportUrl} className={`inline-flex items-center gap-2 rounded-full border-2 border-fg px-4 py-2 text-sm font-bold ${s?.questions ? '' : 'pointer-events-none opacity-50'}`}>
          <Download size={15} aria-hidden="true" />{T.exportXlsx}
        </a>
        <label className="inline-flex cursor-pointer items-center gap-2 rounded-full border-2 border-fg px-4 py-2 text-sm font-bold">
          <Upload size={15} aria-hidden="true" />{T.importXlsx}
          <input type="file" accept=".xlsx" className="sr-only" onChange={async (e) => {
            const f = e.target.files?.[0]; e.target.value = ''
            if (!f) return
            try { const r = await api.contacts.importFile(f); setSt(r); toast('success', T.imported(r.corrections)) } catch (err) { fail(err) }
          }} />
        </label>
        {st && !st.outlook && <p className="w-full text-sm font-bold text-warning">{T.noOutlook}</p>}
        {st?.state.message && <p className="w-full text-sm font-bold" aria-live="polite">{st.state.message}</p>}
        {st?.state.error && <p role="alert" className="w-full text-sm font-bold text-danger">{st.state.error}</p>}
      </section>
      {s && s.questions > 0 ? (
        <section data-enter className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-5">
          <p className="text-sm font-bold">{T.summary(s.questions, s.asked, Object.keys(s.teams).length)}{s.to_check ? ` · ${T.toCheck(s.to_check)}` : ''} · {s.built_at}</p>
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            <TextInput aria-label={T.search} placeholder={T.search} value={q} onChange={(e) => setQ(e.target.value)} />
            <Select aria-label={T.allTeams} value={team} onChange={(e) => setTeam(e.target.value)}>
              <option value="">{T.allTeams}</option>
              {Object.entries(s.teams).map(([t, n]) => <option key={t} value={t}>{t} ({n})</option>)}
            </Select>
            <Select aria-label={T.allDd} value={dd} onChange={(e) => setDd(e.target.value)}>
              <option value="">{T.allDd}</option>
              {Object.entries(s.dd_types).map(([t, n]) => <option key={t} value={t}>{t} ({n})</option>)}
            </Select>
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[48rem] text-sm">
              <thead className="text-left text-xs uppercase tracking-wider text-fg-3">
                <tr><th className="p-2">Question</th><th className="p-2">Équipe</th><th className="p-2">Personnes</th><th className="p-2">Due diligence</th><th className="p-2">Fois</th></tr>
              </thead>
              <tbody>
                {rows.map((g) => (
                  <tr key={g.question} className={`border-t border-fg/10 align-top ${g.check ? 'bg-[#ffff00]/20' : ''}`}>
                    <td className="p-2 font-semibold">{g.question}{g.variants.length > 1 && <span className="block text-xs text-fg-3">+ {g.variants.length - 1} formulation(s)</span>}</td>
                    <td className="p-2 font-bold">{g.team}{g.corrected ? ' ✓' : ''}</td>
                    <td className="p-2 text-xs">{g.people.join(', ')}</td>
                    <td className="p-2 text-xs">{Object.keys(g.dd_types).join(', ')}</td>
                    <td className="p-2 tabular-nums">{g.times}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : <p className="text-sm font-semibold text-fg-2">{T.empty}</p>}
    </div>
  )
}
