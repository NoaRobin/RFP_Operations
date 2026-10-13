/** Deuxième avis Copilot : pack à ouvrir sur le poste, réimport des réponses citées (toujours « à vérifier »). */
import { useRef, useState } from 'react'
import { Bot, Download, Upload } from 'lucide-react'
import { Button } from '../ui/Button'
import { Switch } from '../ui/Field'
import { useToast } from '../ui/Toast'
import { texts } from '../../content/texts'
import { api, ApiError } from '../../lib/api'
import type { CopilotAnswers, RfiRequest } from '../../lib/types'

export function CopilotPanel({ docId, filename, request, onAnswers }: {
  docId: string; filename: string; request: () => RfiRequest; onAnswers: (a: CopilotAnswers) => void
}) {
  const toast = useToast()
  const input = useRef<HTMLInputElement>(null)
  const [all, setAll] = useState(false)
  const [busy, setBusy] = useState<'pack' | 'import' | null>(null)
  const [rejected, setRejected] = useState<CopilotAnswers['rejected']>([])

  const fail = (e: unknown) => toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)

  const pack = async () => {
    setBusy('pack')
    try {
      const blob = await api.rfi.copilotPack(docId, request(), all)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `Pack_Copilot_${filename.replace(/\.[^.]+$/, '').slice(0, 40)}.zip`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      fail(e)
    } finally {
      setBusy(null)
    }
  }

  const upload = async (file: File | undefined) => {
    if (!file) return
    setBusy('import')
    try {
      const r = await api.rfi.copilotAnswers(docId, file, request())
      setRejected(r.rejected)
      const n = Object.keys(r.overrides).length
      toast(n ? 'success' : 'info', n ? texts.copilot.imported(n, r.rejected.length) : texts.copilot.none)
      if (n) onAnswers(r)
    } catch (e) {
      fail(e)
    } finally {
      setBusy(null)
      if (input.current) input.current.value = ''
    }
  }

  return (
    <div className="rounded-2xl border-2 border-fg bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-full border-2 border-fg bg-magic-400 text-white"><Bot size={20} aria-hidden="true" /></span>
          <div>
            <p className="font-display text-lg font-semibold">{texts.copilot.title}</p>
            <p className="max-w-2xl text-sm font-semibold text-fg-2">{texts.copilot.lead}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Switch checked={all} onChange={setAll} label={texts.copilot.packAll} />
          <Button size="sm" variant="secondary" onClick={pack} loading={busy === 'pack'} icon={<Download size={16} />}>{texts.copilot.pack}</Button>
          <Button size="sm" variant="secondary" onClick={() => input.current?.click()} loading={busy === 'import'} icon={<Upload size={16} />}>{texts.copilot.import}</Button>
          <input ref={input} type="file" accept=".xlsx,.zip" className="sr-only" onChange={(e) => void upload(e.target.files?.[0])} />
        </div>
      </div>
      {rejected.length > 0 && (
        <details className="mt-3 text-sm font-semibold">
          <summary className="cursor-pointer text-warning">{texts.copilot.rejected} ({rejected.length})</summary>
          <ul className="mt-2 space-y-1 text-fg-2">
            {rejected.map((r) => <li key={r.id}><span className="text-fg">{r.question}</span> — {r.reason}</li>)}
          </ul>
        </details>
      )}
    </div>
  )
}
