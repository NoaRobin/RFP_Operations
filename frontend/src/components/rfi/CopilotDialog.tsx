/**
 * Copilot en trois gestes : 1. joindre le DIC et le prospectus, 2. copier le prompt (format de retour imposé),
 * 3. coller la réponse. L'app montre ce qu'elle a compris, ligne à ligne, avant d'appliquer (toujours « à vérifier »).
 * Gros questionnaire : le prompt est découpé en lots, à coller l'un après l'autre.
 */
import { useEffect, useState } from 'react'
import { Check, Clipboard, Download, ExternalLink, FileSpreadsheet, Loader2, Upload } from 'lucide-react'
import { Button } from '../ui/Button'
import { Dialog } from '../ui/Dialog'
import { Switch } from '../ui/Field'
import { useToast } from '../ui/Toast'
import { texts } from '../../content/texts'
import { api, ApiError } from '../../lib/api'
import type { CopilotAnswers, CopilotPrompt, RfiRequest } from '../../lib/types'

const C = texts.copilot

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section className="flex gap-3">
      <span className="grid size-8 shrink-0 place-items-center rounded-full border-2 border-fg bg-sun-400 font-display font-bold">{n}</span>
      <div className="min-w-0 flex-1">
        <h3 className="font-display text-lg font-semibold">{title}</h3>
        <div className="mt-1.5">{children}</div>
      </div>
    </section>
  )
}

export function CopilotDialog({ open, onClose, docId, filename, request, onApply }: {
  open: boolean; onClose: () => void; docId: string; filename: string; request: () => RfiRequest
  onApply: (overrides: CopilotAnswers['overrides']) => void
}) {
  const toast = useToast()
  const [all, setAll] = useState(false)
  const [prompt, setPrompt] = useState<CopilotPrompt | null>(null)
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState<number | null>(null)
  const [reply, setReply] = useState('')
  const [reading, setReading] = useState(false)
  const [parsed, setParsed] = useState<CopilotAnswers | null>(null)
  const [keep, setKeep] = useState<Set<string>>(new Set())
  const fail = (e: unknown) => toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)

  useEffect(() => {
    if (!open) return
    setLoading(true)
    setParsed(null)
    api.rfi.copilotPrompt(docId, request(), all).then(setPrompt).catch(fail).finally(() => setLoading(false))
  }, [open, all]) // eslint-disable-line react-hooks/exhaustive-deps

  const copy = async (i: number) => {
    if (!prompt) return
    try {
      await navigator.clipboard.writeText(prompt.batches[i].prompt)
      setCopied(i)
    } catch {
      toast('error', C.copyFailed)
    }
  }
  const read = async () => {
    if (!prompt) return
    setReading(true)
    try {
      const r = await api.rfi.copilotReply(docId, request(), reply, prompt.labels)
      setParsed(r)
      setKeep(new Set(Object.keys(r.overrides)))
    } catch (e) { fail(e) } finally { setReading(false) }
  }
  const apply = () => {
    if (!parsed) return
    const chosen = Object.fromEntries(Object.entries(parsed.overrides).filter(([id]) => keep.has(id)))
    onApply(chosen)
    toast('success', C.applied(Object.keys(chosen).length))
    setParsed(null)
    setReply('')
  }
  const importFile = async (file: File) => {
    try {
      const r = await api.rfi.copilotAnswers(docId, file, request())
      setParsed(r)
      setKeep(new Set(Object.keys(r.overrides)))
    } catch (e) { fail(e) }
  }
  const pack = async () => {
    try {
      const blob = await api.rfi.copilotPack(docId, request(), all)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `Pack_Copilot_${filename.replace(/\.[^.]+$/, '').slice(0, 40)}.zip`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) { fail(e) }
  }

  const lines = parsed?.lines ?? []
  return (
    <Dialog open={open} onClose={onClose} title={C.title} size="lg"
      footer={parsed ? (
        <>
          <Button variant="ghost" onClick={() => setParsed(null)}>{C.back}</Button>
          <Button variant="primary" onClick={apply} disabled={keep.size === 0} icon={<Check size={16} />}>{C.apply(keep.size)}</Button>
        </>
      ) : undefined}>
      {loading && !prompt ? <p className="flex items-center gap-2 font-semibold text-fg-2"><Loader2 size={16} className="motion-safe:animate-spin" />{C.preparing}</p> : prompt && !parsed ? (
        <div className="flex flex-col gap-5">
          <p className="text-sm font-semibold text-fg-2">{C.lead(prompt.count)}</p>
          <Step n={1} title={C.step1}>
            {prompt.documents.length ? (
              <div className="flex flex-wrap gap-2">
                {prompt.documents.map((d) => (
                  <a key={d.name || d.url} href={d.download || d.url} download={d.download ? d.name : undefined} target={d.download ? undefined : '_blank'} rel="noreferrer"
                    className="inline-flex items-center gap-1.5 rounded-full border-2 border-fg bg-card px-3 py-1 text-sm font-bold hover:bg-sun-400">
                    <Download size={14} aria-hidden="true" />{texts.review.sourceKind[d.kind] ?? d.title}
                  </a>
                ))}
              </div>
            ) : <p className="text-sm font-semibold text-warning">{C.noDocs}</p>}
            <p className="mt-1 text-xs font-semibold text-fg-3">{C.attach}</p>
          </Step>
          <Step n={2} title={prompt.batches.length > 1 ? C.step2Batches(prompt.batches.length) : C.step2}>
            <div className="flex flex-wrap items-center gap-2">
              {prompt.batches.map((b, i) => (
                <Button key={i} size="sm" variant={copied === i ? 'secondary' : 'primary'} onClick={() => copy(i)} icon={copied === i ? <Check size={14} /> : <Clipboard size={14} />}>
                  {prompt.batches.length > 1 ? C.copyBatch(i + 1, b.labels.length) : C.copy(b.labels.length)}
                </Button>
              ))}
              <a href={C.copilotUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm font-bold text-magic-300 underline">
                {C.open}<ExternalLink size={12} aria-hidden="true" />
              </a>
            </div>
            <div className="mt-2"><Switch checked={all} onChange={setAll} label={C.includeAuto} /></div>
            <details className="mt-2 text-xs">
              <summary className="cursor-pointer font-bold text-fg-3">{C.preview}</summary>
              <pre className="mt-1 max-h-56 overflow-auto whitespace-pre-wrap rounded-xl border-2 border-fg/20 bg-card-2 p-2 font-mono text-[0.7rem]">{prompt.batches[0]?.prompt}</pre>
            </details>
          </Step>
          <Step n={3} title={C.step3}>
            <textarea value={reply} onChange={(e) => setReply(e.target.value)} rows={6} placeholder={C.pastePlaceholder} aria-label={C.step3}
              className="w-full rounded-xl border-2 border-fg bg-card p-2 font-mono text-xs" />
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Button onClick={read} loading={reading} disabled={!reply.trim()} variant="primary">{C.read}</Button>
              <span className="text-xs font-semibold text-fg-3">{C.readHint}</span>
            </div>
          </Step>
          <details className="rounded-xl border-2 border-dashed border-fg/30 p-3 text-sm">
            <summary className="cursor-pointer font-bold"><FileSpreadsheet size={14} className="mr-1 inline" aria-hidden="true" />{C.excelWay}</summary>
            <p className="mt-1 text-xs font-semibold text-fg-2">{C.excelHint}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button size="sm" onClick={pack} icon={<Download size={14} />}>{C.pack}</Button>
              <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-full border-2 border-fg bg-card px-3 py-1 text-sm font-bold hover:bg-sun-400">
                <Upload size={14} aria-hidden="true" />{C.import}
                <input type="file" accept=".xlsx,.zip" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) void importFile(f); e.target.value = '' }} />
              </label>
            </div>
          </details>
        </div>
      ) : parsed ? (
        <div>
          <p className="text-sm font-semibold text-fg-2">{C.understood(Object.keys(parsed.overrides).length, lines.length)}</p>
          {(parsed.unknown?.length ?? 0) > 0 && <p className="mt-1 text-xs font-semibold text-warning">{C.unknown(parsed.unknown!.join(', '))}</p>}
          <ul className="mt-3 flex flex-col gap-1.5">
            {lines.map((l) => (
              <li key={l.id} className={`rounded-xl border-2 p-2 text-sm ${l.verdict === 'ok' ? 'border-fg bg-card' : 'border-fg/20 bg-card-2 opacity-80'}`}>
                <label className="flex items-start gap-2">
                  <input type="checkbox" disabled={l.verdict !== 'ok'} checked={keep.has(l.id)} className="mt-1 accent-[var(--color-magic-500)]"
                    onChange={(e) => setKeep((k) => { const n = new Set(k); if (e.target.checked) n.add(l.id); else n.delete(l.id); return n })} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-xs font-semibold text-fg-3">{l.question}</span>
                    <span className="font-semibold">{l.answer}</span>
                    {l.citation && <span className="text-xs font-semibold text-fg-3"> · {l.citation}{l.confidence ? ` · ${l.confidence}` : ''}</span>}
                    {l.verdict === 'ok' && l.differs && <span className="block text-xs font-bold text-bubble-300">{C.differs(l.previous ?? '')}</span>}
                    {l.verdict !== 'ok' && <span className="block text-xs font-bold text-warning">{l.verdict === 'not_found' ? C.notFound : l.reason}</span>}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </Dialog>
  )
}
