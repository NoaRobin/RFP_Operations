/** Analyse IA par Copilot (sans API) : prompt(s) à copier, réponse à coller, constats ajoutés à la carte. */
import { useState } from 'react'
import { Bot, ClipboardCopy } from 'lucide-react'
import { texts } from '../../content/texts'
import { api, ApiError } from '../../lib/api'
import type { QvidianAiPrompt } from '../../lib/types'
import { Button } from '../ui/Button'
import { TextArea } from '../ui/Field'
import { useToast } from '../ui/Toast'

const Q = texts.qvidian

export function AiPanel({ ids, onDone }: { ids: number[]; onDone: () => void }) {
  const toast = useToast()
  const [prompt, setPrompt] = useState<QvidianAiPrompt | null>(null)
  const [copied, setCopied] = useState<number | null>(null)
  const [reply, setReply] = useState('')
  const [busy, setBusy] = useState(false)
  const fail = (e: unknown) => toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)

  const prepare = async () => {
    setBusy(true)
    try { setPrompt(await api.qvidian.aiPrompt(ids)); setCopied(null); setReply('') } catch (e) { fail(e) } finally { setBusy(false) }
  }
  const copy = async (i: number) => {
    if (!prompt) return
    try { await navigator.clipboard.writeText(prompt.batches[i].prompt); setCopied(i) } catch { toast('error', Q.copyFailed) }
  }
  const read = async () => {
    if (!prompt) return
    setBusy(true)
    try {
      const r = await api.qvidian.aiReply(reply, prompt.batches.flatMap((b) => b.ids))
      toast('success', Q.aiDone(r.saved))
      setPrompt(null)
      setReply('')
      onDone()
    } catch (e) { fail(e) } finally { setBusy(false) }
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm font-semibold text-fg-2">{Q.aiLead}</p>
      <Button onClick={prepare} disabled={ids.length === 0 || busy} loading={busy && !prompt} icon={<Bot size={17} />}>{Q.aiPrepare(ids.length)}</Button>
      {prompt && (
        <>
          <div className="flex flex-wrap gap-2">
            {prompt.batches.map((_, i) => (
              <Button key={i} size="sm" variant={copied === i ? 'primary' : 'secondary'} onClick={() => copy(i)} icon={<ClipboardCopy size={15} />}>
                {copied === i ? Q.aiCopied : Q.aiCopy(i + 1, prompt.batches.length)}
              </Button>
            ))}
          </div>
          <details className="text-xs">
            <summary className="cursor-pointer font-bold">Voir le prompt</summary>
            <pre className="mt-1 max-h-60 overflow-auto whitespace-pre-wrap rounded-xl border border-fg/20 bg-card-2 p-2">{prompt.batches[copied ?? 0].prompt}</pre>
          </details>
          <label className="text-sm font-bold" htmlFor="qv-ai-reply">{Q.aiPaste}</label>
          <TextArea id="qv-ai-reply" rows={6} value={reply} onChange={(e) => setReply(e.target.value)} placeholder="| C1012 | depasse | moyenne | … | … |" />
          <Button variant="primary" onClick={read} disabled={!reply.trim() || busy} loading={busy}>{Q.aiRead}</Button>
        </>
      )}
    </div>
  )
}
