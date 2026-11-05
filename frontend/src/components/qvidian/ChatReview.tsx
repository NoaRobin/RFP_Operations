/**
 * Relecture complète par un chat : export des textes en JSON (avec le prompt et le format de retour imposé), à déposer
 * dans le chat, qui rend un Excel à onglets (textes dépassés, orthographe, incohérences, erreurs, code, forme) ;
 * l'Excel réimporté range chaque constat sur son texte (carte des erreurs, ici). Rien n'est écrit dans Qvidian.
 */
import { useState } from 'react'
import { Download, Upload } from 'lucide-react'
import { texts } from '../../content/texts'
import { api, ApiError } from '../../lib/api'
import { Button } from '../ui/Button'
import { useToast } from '../ui/Toast'

const C = texts.qviapi

export function ChatReview({ ids, onDone }: { ids: number[]; onDone: () => void }) {
  const toast = useToast()
  const [busy, setBusy] = useState<'export' | 'import' | null>(null)
  const fail = (e: unknown) => toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
  const exportPack = async (all: boolean) => {
    setBusy('export')
    try {
      const { blob, name } = await api.qvidian.aiExport(all ? [] : ids)
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob); a.download = name; a.click(); URL.revokeObjectURL(a.href)
      toast('success', C.chatExported)
    } catch (e) { fail(e) } finally { setBusy(null) }
  }
  const importXlsx = async (files: FileList | null) => {
    if (!files?.length) return
    setBusy('import')
    try {
      const r = await api.qvidian.aiImportXlsx(Array.from(files))
      toast('success', C.chatImported(r.read, r.texts), r.unknown.length ? C.chatUnknown(r.unknown.length) : undefined)
      onDone()
    } catch (e) { fail(e) } finally { setBusy(null) }
  }
  return (
    <div className="flex flex-col gap-3">
      <h2 className="text-lg">{C.chatTitle}</h2>
      <ol className="flex flex-col gap-1.5 text-sm text-fg-2">
        {C.chatSteps.map((s, i) => <li key={i} className="flex gap-2"><span className="qv-meter text-fg-3">{i + 1}</span><span>{s}</span></li>)}
      </ol>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="primary" loading={busy === 'export'} onClick={() => void exportPack(true)} icon={<Download size={14} />}>{C.chatExportAll}</Button>
        <Button size="sm" disabled={!ids.length} loading={busy === 'export'} onClick={() => void exportPack(false)} icon={<Download size={14} />}>{C.chatExportSel(ids.length)}</Button>
        <label className={`inline-flex cursor-pointer items-center gap-2 rounded-full border border-fg/30 px-4 py-1.5 text-sm font-semibold hover:border-fg ${busy ? 'pointer-events-none opacity-60' : ''}`}>
          <Upload size={14} aria-hidden="true" />{C.chatImport}
          <input type="file" accept=".xlsx" multiple className="sr-only" onChange={(e) => { void importXlsx(e.target.files); e.target.value = '' }} />
        </label>
      </div>
      <p className="text-xs text-fg-3">{C.chatNote}</p>
    </div>
  )
}
