/**
 * Agent Copilot : la bibliothèque Qvidian écrite dans un dossier SharePoint synchronisé, lu par l'agent comme source
 * de connaissances, et remise à jour après chaque synchronisation (merlin/qvidian/agent_export.py). Lecture seule
 * pour Qvidian ; seuls les fichiers écrits par l'export sont modifiés ou retirés.
 */
import { useEffect, useState } from 'react'
import { ClipboardCopy, FolderSync } from 'lucide-react'
import { Button } from '../../../components/ui/Button'
import { Switch, TextInput } from '../../../components/ui/Field'
import { ErrorState, Loading } from '../../../components/ui/States'
import { useToast } from '../../../components/ui/Toast'
import { texts } from '../../../content/texts'
import { api, ApiError } from '../../../lib/api'
import type { AgentExportState } from '../../../lib/types'

const A = texts.qviapi.agent

export function AgentView() {
  const toast = useToast()
  const [state, setState] = useState<AgentExportState | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [path, setPath] = useState('')
  const [mode, setMode] = useState<'texts' | 'bundles'>('texts')
  const [expired, setExpired] = useState(true)
  const [auto, setAuto] = useState(true)
  const [busy, setBusy] = useState(false)

  const adopt = (s: AgentExportState) => { setState(s); setPath(s.path); setMode(s.mode); setExpired(s.include_expired); setAuto(s.auto) }
  useEffect(() => { api.qvidian.agentExport().then(adopt).catch((e) => setError(e instanceof ApiError ? e : new ApiError(String(e)))) }, [])

  const run = async () => {
    setBusy(true)
    try {
      adopt(await api.qvidian.agentExportRun({ path, mode, include_expired: expired, auto }))
    } catch (e) {
      toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
    } finally {
      setBusy(false)
    }
  }
  const copy = async () => {
    if (!state) return
    try { await navigator.clipboard.writeText(state.instructions); toast('success', A.copied) } catch { /* presse-papiers refusé : le texte reste sélectionnable */ }
  }

  if (error) return <ErrorState error={error} />
  if (!state) return <Loading />
  return (
    <div className="flex flex-col gap-5">
      <header data-enter>
        <h1 className="text-2xl font-semibold">{A.title}</h1>
        <p className="mt-2 max-w-3xl text-sm font-semibold text-fg-2">{A.lead}</p>
      </header>
      {state.source !== 'qvidian' && <p role="note" className="rounded-[var(--radius-card)] border border-line bg-card p-3 text-sm text-warning">{A.demo}</p>}

      <section data-enter className="flex flex-col gap-4 rounded-[var(--radius-card)] border border-line bg-card p-5">
        <label className="flex flex-col gap-1 text-sm font-semibold">{A.path}
          <TextInput value={path} onChange={(e) => setPath(e.target.value)} placeholder="C:\Users\…\Agent Qvidian" spellCheck={false} />
          <span className="text-xs font-normal text-fg-3">{A.pathHint}</span>
        </label>
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-sm font-semibold">{A.mode}</legend>
          {([['texts', A.modeTexts, A.modeTextsHint], ['bundles', A.modeBundles(state.max_bundles), A.modeBundlesHint]] as const).map(([value, label, hint]) => (
            <label key={value} className="flex cursor-pointer items-start gap-3 rounded-md border border-line p-3">
              <input type="radio" name="agent-mode" className="mt-1" checked={mode === value} onChange={() => setMode(value)} />
              <span><span className="block text-sm font-semibold">{label}</span><span className="block text-xs text-fg-3">{hint}</span></span>
            </label>
          ))}
        </fieldset>
        <Switch checked={expired} onChange={setExpired} label={A.expired} />
        <Switch checked={auto} onChange={setAuto} label={A.auto} />
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="primary" icon={<FolderSync size={16} />} disabled={busy || !path.trim()} onClick={run}>{busy ? A.running : A.run}</Button>
          <p className="text-sm text-fg-2" aria-live="polite">
            {state.last ? <>{A.last} : <span className="qv-meter">{state.last.at.replace('T', ' ')}</span> · {A.summary(state.last)}</> : A.never}
          </p>
        </div>
        {state.error && <p role="alert" className="text-sm font-semibold text-danger">{state.error}</p>}
        <p className="text-xs text-fg-3">{A.delay}</p>
      </section>

      <section data-enter className="rounded-[var(--radius-card)] border border-line bg-card p-5">
        <h2 className="text-lg">{A.stepsTitle}</h2>
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm">{A.steps.map((s) => <li key={s}>{s}</li>)}</ol>
        <div className="mt-4 flex items-center gap-3">
          <h3 className="text-sm font-semibold">{A.instructions}</h3>
          <Button size="sm" icon={<ClipboardCopy size={14} />} onClick={copy}>{A.copy}</Button>
        </div>
        <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap rounded-md border border-line bg-field p-3 text-xs" tabIndex={0}>{state.instructions}</pre>
      </section>
    </div>
  )
}
