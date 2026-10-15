/** Documents officiels de la part choisie : trouvés sur le site, dans un dossier, ou déposés à la main. */
import { useEffect, useState } from 'react'
import { BookOpen, FileText, RefreshCw, Upload } from 'lucide-react'
import { texts } from '../../content/texts'
import { api, ApiError } from '../../lib/api'
import type { FundDocuments as Docs } from '../../lib/types'

export function FundDocuments({ isin }: { isin: string | null }) {
  const [docs, setDocs] = useState<Docs | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const T = texts.fundDocs

  const run = async (loader: () => Promise<Docs>) => {
    setBusy(true)
    setError(null)
    try { setDocs(await loader()) } catch (e) { setError(e instanceof ApiError ? `${e.message} ${e.hint}` : String(e)) } finally { setBusy(false) }
  }
  useEffect(() => { setDocs(null); if (isin) void run(() => api.rfi.fundDocuments(isin)) }, [isin]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!isin) return null
  return (
    <div className="rounded-2xl border-2 border-fg bg-card p-4">
      <p className="flex items-center gap-2 font-display text-lg font-semibold"><FileText size={18} aria-hidden="true" />{T.title}</p>
      {busy && <p className="mt-1 text-sm font-semibold text-fg-2" aria-live="polite">{T.searching}</p>}
      {error && <p role="alert" className="mt-1 text-sm font-semibold text-danger">{error}</p>}
      {docs && (
        <>
          {docs.documents.length > 0 ? (
            <ul className="mt-2 flex flex-col gap-1 text-sm font-semibold">
              {docs.documents.map((d) => (
                <li key={d.path || d.url} className="flex items-center gap-2">
                  {d.kind === 'kid' ? <FileText size={15} aria-hidden="true" /> : <BookOpen size={15} aria-hidden="true" />}
                  <a href={d.url} target="_blank" rel="noreferrer" className="truncate underline">{T.kinds[d.kind] ?? d.kind} · {d.title}</a>
                  <span className="shrink-0 text-xs text-fg-3">{d.source}{d.doc_date ? ` · ${d.doc_date}` : ''}</span>
                </li>
              ))}
            </ul>
          ) : <p className="mt-1 text-sm font-semibold text-fg-2">{T.none}</p>}
          {docs.facts.length > 0 && <p className="mt-2 inline-block rounded-full border-2 border-fg bg-mint-400 px-2.5 py-0.5 text-xs font-bold">{T.found(docs.facts.length)}</p>}
          {docs.problems.length > 0 && <ul className="mt-2 text-xs font-semibold text-warning">{docs.problems.slice(0, 3).map((p) => <li key={p}>⚠ {p}</li>)}</ul>}
        </>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <label className={`inline-flex cursor-pointer items-center gap-1.5 rounded-full border-2 border-fg px-3 py-1 text-xs font-bold ${busy ? 'pointer-events-none opacity-60' : ''}`}>
          <Upload size={13} aria-hidden="true" />{T.upload}
          <input type="file" accept=".pdf,application/pdf" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) void run(() => api.rfi.uploadFundDocument(isin, f)); e.target.value = '' }} />
        </label>
        <button onClick={() => run(() => api.rfi.fundDocuments(isin, true))} disabled={busy} className="inline-flex items-center gap-1.5 rounded-full border-2 border-fg/40 px-3 py-1 text-xs font-bold">
          <RefreshCw size={13} aria-hidden="true" />{T.refresh}
        </button>
      </div>
    </div>
  )
}
