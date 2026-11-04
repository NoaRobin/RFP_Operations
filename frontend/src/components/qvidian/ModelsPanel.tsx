/**
 * Modèles de recherche : packs Rapide / Précis en un clic, avancement, diagnostic clair quand le proxy bloque (hôte refusé),
 * et installation depuis le navigateur (liens + dépôt des fichiers, reconnus par empreinte) en repli.
 */
import { useState } from 'react'
import { CheckCircle2, Copy, Download, ExternalLink, FolderSearch, Square, Upload } from 'lucide-react'
import { texts } from '../../content/texts'
import { api } from '../../lib/api'
import type { QvidianEngineStatus } from '../../lib/types'
import { Button } from '../ui/Button'
import { TextInput } from '../ui/Field'
import { useToast } from '../ui/Toast'
import { Bar, copyText } from './Bits'

const Q = texts.qvidian

export function ModelsPanel({ engine, onChange, fail }: { engine: QvidianEngineStatus | null; onChange: (e?: QvidianEngineStatus) => void; fail: (e: unknown) => void }) {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [folder, setFolder] = useState('')
  const [it, setIt] = useState<string | null>(null)
  const models = engine?.models ?? []
  const byId = Object.fromEntries(models.map((m) => [m.id, m]))
  const blocked = models.map((m) => m.download).find((d) => d?.error && d.hint)
  const missing = models.filter((m) => !m.installed && (m.packs ?? []).length)
  const installed = (r: { installed: unknown[]; ready: string[]; engine: QvidianEngineStatus }) => {
    toast(r.installed.length ? 'success' : 'error', r.installed.length ? Q.manualDone(r.installed.length, r.ready) : Q.manualNone)
    onChange(r.engine)
  }
  const upload = async (files: FileList | null) => {
    if (!files?.length) return
    setBusy(true)
    try { installed(await api.qvidian.uploadModels(Array.from(files))) } catch (e) { fail(e) } finally { setBusy(false) }
  }
  const scan = async (path = '') => {
    setBusy(true)
    try { installed(await api.qvidian.scanModels(path)) } catch (e) { fail(e) } finally { setBusy(false) }
  }
  const showIt = async () => {
    try {
      const packs = (engine?.packs ?? []).filter((p) => !p.installed).map((p) => p.id)
      const texts_ = await Promise.all((packs.length ? packs : ['rapide']).map((p) => api.qvidian.itRequest(p)))
      setIt(texts_.map((t) => t.text).join('\n\n'))
    } catch (e) { fail(e) }
  }
  return (
    <div className="flex flex-col gap-4">
      <p className="max-w-3xl text-sm font-semibold text-fg-2">{Q.packsLead}</p>
      <ul className="grid gap-3 md:grid-cols-2">
        {(engine?.packs ?? []).map((p) => {
          const parts = p.models.map((id) => byId[id]).filter(Boolean)
          const running = parts.some((m) => m.download?.running)
          const done = parts.reduce((a, m) => a + (m.installed ? m.size_mb * 1e6 : (m.download?.done ?? 0)), 0)
          const total = parts.reduce((a, m) => a + m.size_mb * 1e6, 0) || 1
          const via = parts.map((m) => m.download?.via).find(Boolean)
          return (
            <li key={p.id} className={`flex flex-col gap-2 rounded-2xl border-[2.5px] p-4 ${p.installed ? 'border-fg bg-mint-400/15' : 'border-fg bg-card'}`}>
              <p className="font-display text-lg font-semibold">{p.label}</p>
              <p className="text-xs font-semibold text-fg-2">{p.note}</p>
              <p className="text-xs font-semibold text-fg-3">{parts.map((m) => m.label).join(' + ')}</p>
              {running ? (
                <div aria-live="polite">
                  <p className="text-xs font-bold">{Q.downloading} {Math.round((100 * done) / total)} %{via ? ` · ${Q.packVia(via)}` : ''}</p>
                  <Bar value={done / total} tone="bg-magic-400" />
                  <Button size="sm" variant="ghost" className="mt-2" onClick={async () => { try { onChange(await api.qvidian.stopDownloads()) } catch (e) { fail(e) } }} icon={<Square size={13} />}>{Q.packStop}</Button>
                </div>
              ) : p.installed ? (
                <p className="inline-flex items-center gap-1 text-sm font-bold"><CheckCircle2 size={15} aria-hidden="true" />{Q.packInstalled}</p>
              ) : (
                <Button size="sm" variant="primary" className="self-start" disabled={!engine?.neural_runtime}
                  onClick={async () => { try { onChange(await api.qvidian.downloadPack(p.id)) } catch (e) { fail(e) } }}
                  icon={<Download size={14} />}>{Q.packInstall(p.size_mb)}</Button>
              )}
            </li>
          )
        })}
      </ul>
      {blocked && (
        <div role="alert" className="rounded-2xl border-2 border-danger bg-bubble-400/15 p-4 text-sm">
          <p className="font-bold">{Q.blockedTitle}{blocked.host ? ` (${blocked.host})` : ''}</p>
          <p className="mt-1 font-semibold text-fg-2">{blocked.hint}</p>
          {!!blocked.attempts?.length && (
            <ul className="mt-2 text-xs font-semibold text-fg-3">{blocked.attempts.map((a, i) => <li key={i}>{a.via} : {a.error}</li>)}</ul>
          )}
          <p className="mt-2 text-xs font-semibold text-fg-2">{Q.withoutModels}</p>
          <div className="mt-3">
            {it == null ? <Button size="sm" onClick={showIt}>{Q.itTitle}</Button> : (
              <div className="flex flex-col gap-2">
                <p className="text-xs font-semibold text-fg-2">{Q.itLead}</p>
                <textarea readOnly value={it} rows={10} className="w-full rounded-xl border-2 border-fg/30 bg-card p-2 font-mono text-xs" aria-label={Q.itTitle} />
                <Button size="sm" className="self-start" icon={<Copy size={14} />}
                  onClick={async () => { const ok = await copyText(it); toast(ok ? 'success' : 'error', ok ? Q.itCopied : Q.copyFailed) }}>{Q.itCopy}</Button>
              </div>
            )}
          </div>
        </div>
      )}
      {missing.length > 0 && (
        <details className="rounded-2xl border-2 border-fg/30 p-4" open={!!blocked}>
          <summary className="cursor-pointer font-display font-semibold">{Q.manualTitle}</summary>
          <p className="mt-1 text-xs font-semibold text-fg-2">{Q.manualLead}</p>
          <ul className="mt-3 flex flex-col gap-1.5 text-sm">
            {missing.flatMap((m) => (m.links ?? []).map((l) => (
              <li key={`${m.id}-${l.name}`} className="flex flex-wrap items-center gap-2">
                <a href={l.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-bold underline">
                  <ExternalLink size={13} aria-hidden="true" />{m.label} · {l.name}
                </a>
                <span className="text-xs font-semibold text-fg-3">{Math.round(l.size / 1e6)} Mo</span>
              </li>
            )))}
          </ul>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <label className={`inline-flex cursor-pointer items-center gap-2 rounded-full border-2 border-fg bg-card px-4 py-2 text-sm font-bold ${busy ? 'pointer-events-none opacity-60' : ''}`}>
              <Upload size={15} aria-hidden="true" />{Q.manualDrop}
              <input type="file" multiple accept=".onnx,.json" className="sr-only" onChange={(e) => { void upload(e.target.files); e.target.value = '' }} />
            </label>
            <Button size="sm" onClick={() => void scan()} loading={busy} icon={<FolderSearch size={14} />}>{Q.manualScan}</Button>
          </div>
          <form className="mt-3 flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (folder.trim()) void scan(folder.trim()) }}>
            <label className="flex min-w-[18rem] flex-1 flex-col gap-1 text-xs font-bold">{Q.folderLabel}
              <TextInput value={folder} placeholder={String.raw`\\serveur\partage\modeles`} onChange={(e) => setFolder(e.target.value)} />
            </label>
            <Button type="submit" size="sm" disabled={!folder.trim() || busy}>{Q.folderGo}</Button>
          </form>
        </details>
      )}
      <details className="text-sm">
        <summary className="cursor-pointer font-bold text-fg-3">Détail des modèles</summary>
        <ul className="mt-2 grid gap-2 md:grid-cols-3">
          {models.map((m) => (
            <li key={m.id} className="rounded-xl border-2 border-fg/20 p-3 text-xs">
              <p className="font-bold">{m.label}{m.installed ? ' · installé' : ''}{m.active ? ' · actif' : ''}</p>
              <p className="font-semibold text-fg-3">{m.kind === 'encoder' ? 'Encodeur (sens)' : 'Reranker (lecture fine)'} · {m.size_mb} Mo · {m.license}</p>
              <p className="font-semibold text-fg-3">{m.note}</p>
              {m.error && <p className="font-bold text-danger">{m.error}</p>}
              {m.download?.error && !m.download.hint && <p className="font-bold text-danger">{m.download.error}</p>}
            </li>
          ))}
        </ul>
      </details>
    </div>
  )
}
