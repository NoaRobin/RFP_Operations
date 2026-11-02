/** Fiche d'un contenu : texte, niveau et indices, usage, défauts, versions vues, contenus proches, actions. */
import { Fragment, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { AlertTriangle, ArrowLeft, Check, Copy, PenSquare } from 'lucide-react'
import { Bar, LevelBadge, ago, copyText } from '../../../components/qvidian/Bits'
import { Button } from '../../../components/ui/Button'
import { ErrorState, Loading } from '../../../components/ui/States'
import { useToast } from '../../../components/ui/Toast'
import { texts } from '../../../content/texts'
import { api, ApiError } from '../../../lib/api'
import type { QvidianContent } from '../../../lib/types'
import { useQvidian } from '../context'

const Q = texts.qvidian
const SEV: Record<string, string> = { haute: 'bg-bubble-400', moyenne: 'bg-sun-400', basse: 'bg-mint-400' }

export function ContentView() {
  const { id } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const { selected, toggle, select } = useQvidian()
  const [c, setC] = useState<QvidianContent | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  useEffect(() => {
    setC(null)
    api.qvidian.content(Number(id)).then(setC).catch((e) => setError(e instanceof ApiError ? e : new ApiError(String(e))))
  }, [id])
  if (error) return <ErrorState error={error} />
  if (!c) return <Loading />
  const insight = c.insight
  const meta: [string, string][] = [
    ['Dossier', c.folder_path || '—'], ['Langue', c.language || '—'], ['Type', c.type || '—'], ['Révision', String(c.revision)],
    ['Créé', c.created ?? '—'], ['Modifié', `${c.modified ?? '—'}${c.modified_by ? ` par ${c.modified_by}` : ''}`],
    [Q.lastUsed, `${c.last_used ?? Q.never} (${ago(c.last_used)})`], ['Utilisations', String(c.times_used)],
    ['Expiration', c.expires ?? '—'], ['Propriétaires', c.owners || '—'], ['Statut', `${c.enabled ? 'actif' : 'désactivé'}${c.expired ? ' · expiré' : ''}${c.checked_out ? ` · extrait par ${c.checked_out_by}` : ''}`],
  ]
  const copy = async () => {
    const ok = await copyText(c.text)
    toast(ok ? 'success' : 'error', ok ? Q.copied : Q.copyFailed)
  }
  return (
    <div className="flex flex-col gap-5">
      <div data-enter className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="ghost" onClick={() => navigate(-1)} icon={<ArrowLeft size={15} />}>{Q.back}</Button>
        <span className="text-xs font-bold text-fg-3">#{c.id}</span>
        <span className="ml-auto flex flex-wrap gap-2">
          <Button size="sm" onClick={copy} icon={<Copy size={14} />}>{Q.copy}</Button>
          <Button size="sm" onClick={() => toggle(c.id)} icon={<Check size={14} />}>{selected.has(c.id) ? Q.selectedOne : Q.select}</Button>
          <Button size="sm" variant="primary" onClick={() => { select([c.id]); navigate('/qvidian/modifier?action=set_text') }} icon={<PenSquare size={14} />}>{Q.editThis}</Button>
        </span>
      </div>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <article data-enter className="rounded-[var(--radius-card)] border-[2.5px] border-fg bg-card p-6 shadow-[5px_5px_0_0_var(--color-fg)]">
          <h1 className="font-display text-2xl font-bold leading-tight">{c.title}</h1>
          {c.question && c.question !== c.title && <p className="mt-1 text-sm font-semibold text-fg-2">{c.question}</p>}
          {insight && <div className="mt-3"><LevelBadge level={insight.level} /></div>}
          <p className="mt-4 whitespace-pre-line text-[0.95rem] font-medium leading-relaxed">{c.text || '—'}</p>
          {c.alert_text && <p className="mt-4 rounded-xl bg-sun-400/40 p-3 text-sm font-bold">Alerte : {c.alert_text}</p>}
          {c.learned_terms && <p className="mt-3 text-xs font-semibold text-fg-3">{Q.learnedTerms} : {c.learned_terms}</p>}
          {c.versions.length > 1 && (
            <details className="mt-5 rounded-2xl border-2 border-fg/20 p-3">
              <summary className="cursor-pointer text-sm font-bold">{Q.versions} ({c.versions.length})</summary>
              <ol className="mt-2 flex flex-col gap-3">
                {c.versions.map((v, i) => (
                  <li key={`${v.revision}-${v.seen_at}`} className="border-l-4 border-magic-400/50 pl-3">
                    <p className="text-xs font-bold text-fg-3">rév. {v.revision} · vue le {v.seen_at.slice(0, 10)}{i === 0 ? ' · actuelle' : ''}</p>
                    <p className="whitespace-pre-line text-sm">{v.text}</p>
                  </li>
                ))}
              </ol>
            </details>
          )}
        </article>
        <aside data-enter className="flex flex-col gap-4">
          <section className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-5">
            <h2 className="text-lg">{Q.contentMeta}</h2>
            <dl className="mt-2 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-sm">
              {meta.map(([k, v]) => <Fragment key={k}><dt className="font-bold text-fg-3">{k}</dt><dd className="truncate font-semibold" title={v}>{v}</dd></Fragment>)}
            </dl>
            {insight && (
              <div className="mt-3">
                <p className="text-xs font-bold text-fg-3">{Q.popularity}</p>
                <Bar value={insight.popularity} tone="bg-sun-400" />
              </div>
            )}
          </section>
          {insight?.history && (
            <section className="rounded-[var(--radius-card)] border-2 border-fg bg-sun-400/20 p-5">
              <h2 className="text-lg">{Q.historyChosen(insight.history.files)}</h2>
              <ul className="mt-2 flex flex-col gap-1.5 text-sm">
                {insight.history.examples.map((e, i) => (
                  <li key={i}><span className="font-semibold">« {e.question} »</span><span className="block text-xs font-semibold text-fg-3">{e.file} · {e.date || '—'}{e.fund ? ` · ${e.fund}` : ''} · {e.mode}</span></li>
                ))}
              </ul>
            </section>
          )}
          {insight && (
            <section className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-5">
              <h2 className="text-lg">{Q.clues}</h2>
              <ul className="mt-2 flex flex-wrap gap-1.5">{insight.level.clues.map((x) => <li key={x} className="rounded-full bg-card-2 px-2 py-0.5 text-xs font-semibold">{x}</li>)}</ul>
              <h3 className="mt-4 text-base">Défauts</h3>
              {insight.issues.length === 0 ? <p className="text-sm font-semibold text-fg-3">{Q.noIssue}</p> : (
                <ul className="mt-1 flex flex-col gap-1.5">
                  {insight.issues.map((i, k) => (
                    <li key={k} className="flex items-start gap-2 text-sm font-semibold">
                      <span className={`mt-1.5 size-2.5 shrink-0 rounded-full ${SEV[i.severity]}`} aria-hidden="true" />
                      <span>{i.label} — {i.message}{i.excerpt ? <span className="block text-xs text-fg-3">« {i.excerpt} »</span> : null}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}
          {insight && insight.similar.length > 0 && (
            <section className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-5">
              <h2 className="text-lg">{Q.similar}</h2>
              <ul className="mt-2 flex flex-col gap-2">
                {insight.similar.map((s) => (
                  <li key={s.id} className="text-sm">
                    <Link to={`/qvidian/contenu/${s.id}`} className="font-semibold hover:underline">{s.title}</Link>
                    <span className="block text-xs font-semibold text-fg-3">
                      {s.folder_path} · {Q.uses(s.times_used)}{s.same_text ? ` · ${Q.sameText}` : ''}
                    </span>
                    {s.same_text && <span className="inline-flex items-center gap-1 text-xs font-bold text-warning"><AlertTriangle size={11} aria-hidden="true" />doublon possible</span>}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </aside>
      </div>
    </div>
  )
}
