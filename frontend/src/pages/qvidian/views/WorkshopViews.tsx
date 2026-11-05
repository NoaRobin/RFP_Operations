/**
 * Vues de l'atelier QviAPI : questions déjà tombées (banque des anciens RFI), fraîcheur et échéances (dates de révision
 * proposées), doublons et versions (texte à garder proposé). Lecture seule : les corrections passent par « Modifier ».
 */
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { PenSquare } from 'lucide-react'
import { Button } from '../../../components/ui/Button'
import { Select, TextInput } from '../../../components/ui/Field'
import { ErrorState, Loading } from '../../../components/ui/States'
import { texts } from '../../../content/texts'
import { api, ApiError } from '../../../lib/api'
import type { QvidianBank, QvidianFamily, QvidianFreshness } from '../../../lib/types'
import { useQvidian } from '../context'

const W = texts.qviapi

function Head({ title, lead }: { title: string; lead: string }) {
  return (
    <header data-enter>
      <h1 className="text-[clamp(1.8rem,3.6vw,2.8rem)] font-bold leading-none">{title}</h1>
      <p className="mt-2 max-w-3xl text-sm font-semibold text-fg-2">{lead}</p>
    </header>
  )
}

function useLoad<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  useEffect(() => {
    let alive = true
    load().then((d) => alive && setData(d)).catch((e) => alive && setError(e instanceof ApiError ? e : new ApiError(String(e))))
    return () => { alive = false }
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps
  return { data, error }
}

// ------------------------------------------------------------------ questions déjà tombées
export function QuestionsView() {
  const [q, setQ] = useState('')
  const [only, setOnly] = useState('')
  const [debounced, setDebounced] = useState('')
  useEffect(() => { const t = window.setTimeout(() => setDebounced(q), 250); return () => window.clearTimeout(t) }, [q])
  const { data, error } = useLoad<QvidianBank>(() => api.qvidian.questionBank(debounced, only), [debounced, only])
  return (
    <div className="flex flex-col gap-5">
      <Head title={W.questionsTitle} lead={W.questionsLead} />
      <div data-enter className="flex flex-wrap gap-2">
        <TextInput className="min-w-[16rem] flex-1" value={q} onChange={(e) => setQ(e.target.value)} placeholder={W.questionsFilter} aria-label={W.questionsFilter} />
        <Select value={only} onChange={(e) => setOnly(e.target.value)} aria-label={W.questionsOnly}>
          <option value="">{W.all}</option><option value="covered">{W.covered}</option><option value="orphan">{W.orphan}</option>
        </Select>
      </div>
      {error ? <ErrorState error={error} /> : !data ? <Loading /> : !data.ready ? <p className="text-sm font-semibold">{W.bankBuilding}</p> : (
        <section data-enter className="rounded-[var(--radius-card)] border-2 border-fg bg-card">
          <p className="border-b-2 border-fg/10 px-4 py-2 text-xs font-bold text-fg-3">{W.questionsCount(data.total)}</p>
          <ul>
            {data.items.map((x) => (
              <li key={x.question} className="grid gap-2 border-b border-fg/10 px-4 py-3 last:border-0 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_auto]">
                <div>
                  <p className="font-semibold">« {x.question} »</p>
                  <p className="text-xs font-semibold text-fg-3">{W.inRfis(x.rfis)}{x.last ? ` · ${x.last}` : ''}{x.funds.length ? ` · ${x.funds.join(', ')}` : ''}</p>
                </div>
                <div className="text-sm">
                  {x.covered ? x.contents.map((c) => <Link key={c.id} to={`/qvidian/contenu/${c.id}`} className="block truncate font-semibold hover:underline">#{c.id} · {c.title}</Link>)
                    : <span className="rounded-full bg-bubble-400/25 px-2 py-0.5 text-xs font-bold">{W.noText}</span>}
                </div>
                <Link to={`/qvidian/recherche?q=${encodeURIComponent(x.question)}`} className="self-start text-xs font-bold underline">{W.searchIt}</Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ fraîcheur et échéances
const STATES: { key: string; tone: string }[] = [
  { key: 'en retard', tone: 'bg-bubble-400' }, { key: '30 jours', tone: 'bg-sun-400' }, { key: '90 jours', tone: 'bg-magic-400' }, { key: 'plus tard', tone: 'bg-mint-400' },
]

export function FreshnessView() {
  const navigate = useNavigate()
  const { select } = useQvidian()
  const [state, setState] = useState('en retard')
  const { data, error } = useLoad<QvidianFreshness>(() => api.qvidian.freshness(), [])
  const items = useMemo(() => (data?.items ?? []).filter((x) => x.state === state), [data, state])
  if (error) return <ErrorState error={error} />
  if (!data) return <Loading />
  return (
    <div className="flex flex-col gap-5">
      <Head title={W.freshTitle} lead={W.freshLead} />
      <div data-enter className="grid grid-cols-2 gap-3 md:grid-cols-4" role="tablist" aria-label={W.freshTitle}>
        {STATES.map((s) => (
          <button key={s.key} role="tab" aria-selected={state === s.key} onClick={() => setState(s.key)}
            className={`rounded-2xl border-[2.5px] border-fg p-4 text-left transition-transform ${state === s.key ? `${s.tone} shadow-[4px_4px_0_0_var(--color-fg)]` : 'bg-card hover:-translate-y-0.5'}`}>
            <span className="block font-mono text-3xl font-bold">{data.counts[s.key] ?? 0}</span>
            <span className="text-sm font-bold">{W.states[s.key as keyof typeof W.states]}</span>
          </button>
        ))}
      </div>
      <p className="text-xs font-semibold text-fg-3">{W.withoutExpiry(data.without_expiry)}</p>
      {items.length > 0 && (
        <div className="flex">
          <Button size="sm" variant="primary" icon={<PenSquare size={14} />}
            onClick={() => { select(items.map((x) => x.id)); navigate('/qvidian/modifier?action=expire') }}>{W.planExpiry(items.length)}</Button>
        </div>
      )}
      <section data-enter className="rounded-[var(--radius-card)] border-2 border-fg bg-card">
        {items.length === 0 ? <p className="p-5 text-sm font-semibold">{W.freshNone}</p> : (
          <ul>
            {items.map((x) => (
              <li key={x.id} className="grid gap-1 border-b border-fg/10 px-4 py-3 last:border-0 md:grid-cols-[minmax(0,1.5fr)_10rem_minmax(0,1fr)]">
                <div>
                  <Link to={`/qvidian/contenu/${x.id}`} className="font-semibold hover:underline">{x.title}</Link>
                  <p className="text-xs font-semibold text-fg-3">{x.folder_path} · {W.uses(x.times_used)} · {W.modified(x.modified)}</p>
                </div>
                <p className="font-mono text-sm font-bold">{x.due}<span className="block text-xs font-semibold text-fg-3">{x.expires ? W.expiresOn(x.expires) : W.proposed}</span></p>
                <p className="text-xs font-semibold text-fg-2">{x.why}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

// ------------------------------------------------------------------ doublons et versions
export function DuplicatesView() {
  const navigate = useNavigate()
  const { select } = useQvidian()
  const { data, error } = useLoad<QvidianFamily[]>(() => api.qvidian.families(), [])
  if (error) return <ErrorState error={error} />
  if (!data) return <Loading />
  return (
    <div className="flex flex-col gap-5">
      <Head title={W.dupTitle} lead={W.dupLead(data.length)} />
      {data.length === 0 && <p className="text-sm font-semibold">{W.dupNone}</p>}
      {data.map((f) => (
        <section key={f.keep} data-enter className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-4">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg">{W.family(f.size, f.uses)}</h2>
            <Button size="sm" className="ml-auto" icon={<PenSquare size={14} />}
              onClick={() => { select(f.members.filter((m) => !m.keep).map((m) => m.id)); navigate('/qvidian/modifier?action=disable') }}>{W.disableOthers}</Button>
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            {f.members.map((m) => (
              <article key={m.id} className={`rounded-xl border-2 p-3 ${m.keep ? 'border-fg bg-mint-400/15' : 'border-fg/20'}`}>
                <p className="flex items-center gap-2">
                  {m.keep && <span className="rounded-full bg-mint-400 px-2 text-xs font-bold">{W.keep}</span>}
                  <Link to={`/qvidian/contenu/${m.id}`} className="font-semibold hover:underline">#{m.id} · {m.title}</Link>
                </p>
                <p className="text-xs font-semibold text-fg-3">{m.folder_path} · {W.uses(m.times_used)} · {W.modified(m.modified)}{m.enabled ? '' : ` · ${W.disabled}`}</p>
                <p className="mt-1 line-clamp-4 text-sm">{m.text}</p>
              </article>
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
