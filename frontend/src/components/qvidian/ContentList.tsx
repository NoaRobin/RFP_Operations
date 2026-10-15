/** Liste des contenus (filtrés par la carte) : cases à cocher, défauts, détail avec le texte et ses versions. */
import { useEffect, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { texts } from '../../content/texts'
import { api } from '../../lib/api'
import type { QvidianContent, QvidianItem } from '../../lib/types'

const Q = texts.qvidian
const SEV: Record<string, string> = { haute: 'bg-bubble-400', moyenne: 'bg-sun-400', basse: 'bg-mint-400' }

function Detail({ id }: { id: number }) {
  const [c, setC] = useState<QvidianContent | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let alive = true
    api.qvidian.content(id).then((x) => alive && setC(x)).catch((e) => alive && setError(e.message))
    return () => { alive = false }
  }, [id])
  if (error) return <p className="text-sm text-danger">{error}</p>
  if (!c) return <p className="text-sm text-fg-3">…</p>
  return (
    <div className="mt-2 flex flex-col gap-2 rounded-xl border-2 border-fg/20 bg-card-2 p-3 text-sm">
      <p className="whitespace-pre-line font-semibold">{c.text || '—'}</p>
      <p className="text-xs font-semibold text-fg-3">
        {c.language} · créé {c.created ?? '—'} · modifié {c.modified ?? '—'} · {Q.lastUsed} {c.last_used ?? Q.never} · {Q.uses(c.times_used)}
        {c.expires ? ` · expire ${c.expires}` : ''}{c.checked_out ? ` · extrait par ${c.checked_out_by}` : ''}
      </p>
      {c.versions.length > 1 && (
        <details>
          <summary className="cursor-pointer text-xs font-bold">{Q.versions} ({c.versions.length})</summary>
          <ul className="mt-1 flex flex-col gap-1">
            {c.versions.map((v, i) => (
              <li key={i} className="rounded-lg border border-fg/15 bg-card p-2 text-xs"><b>rév. {v.revision}</b> · {v.modified ?? v.seen_at.slice(0, 10)} — {v.text.slice(0, 300)}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

export function ContentList({ items, selected, onToggle }: { items: QvidianItem[]; selected: Set<number>; onToggle: (id: number, on: boolean) => void }) {
  const [open, setOpen] = useState<number | null>(null)
  return (
    <ul className="flex flex-col gap-2">
      {items.map((it) => (
        <li key={it.id} className={`rounded-2xl border-2 p-3 ${selected.has(it.id) ? 'border-fg bg-sun-400/20' : 'border-fg/20 bg-card'}`}>
          <div className="flex items-start gap-3">
            <input type="checkbox" className="mt-1 size-4 accent-[var(--color-magic-500)]" checked={selected.has(it.id)}
              onChange={(e) => onToggle(it.id, e.target.checked)} aria-label={`Cocher #${it.id}`} />
            <div className="min-w-0 flex-1">
              <button onClick={() => setOpen(open === it.id ? null : it.id)} className="flex w-full items-start gap-1.5 text-left" aria-expanded={open === it.id}>
                {open === it.id ? <ChevronDown size={16} className="mt-0.5 shrink-0" aria-hidden="true" /> : <ChevronRight size={16} className="mt-0.5 shrink-0" aria-hidden="true" />}
                <span className="min-w-0">
                  <span className="font-semibold">#{it.id} · {it.title || '(sans titre)'}</span>
                  <span className="block text-xs font-semibold text-fg-3">
                    {it.folder_path || '—'} · {Q.uses(it.times_used)} · {Q.lastUsed} {it.last_used ?? Q.never}{it.enabled ? '' : ' · désactivé'}
                  </span>
                </span>
              </button>
              {it.issues.length > 0 && (
                <ul className="mt-1.5 flex flex-col gap-1">
                  {it.issues.map((i, k) => (
                    <li key={k} className="flex flex-wrap items-baseline gap-1.5 text-xs">
                      <span className={`rounded-full border border-fg px-1.5 py-px font-bold ${SEV[i.severity] ?? 'bg-card-3'}`}>{i.label}</span>
                      <span className="font-semibold">{i.message}</span>
                      {i.excerpt && <code className="rounded bg-card-2 px-1 text-[0.7rem]">{i.excerpt}</code>}
                      {i.fix && <span className="text-fg-2">→ {i.fix}</span>}
                    </li>
                  ))}
                </ul>
              )}
              {open === it.id && <Detail id={it.id} />}
            </div>
          </div>
        </li>
      ))}
    </ul>
  )
}
