/**
 * Merge codes Qvidian : le bot « mergecode » (repris tel quel) rendu digeste.
 * Référentiel Excel une fois pour toutes → export Word → validation d'un clic par passage → Word + compte rendu.
 */
import { useMemo, useRef, useState } from 'react'
import { Check, Download, FileText, RotateCcw, Sparkles, Tags, TriangleAlert, Upload, X } from 'lucide-react'
import { Dropzone } from '../components/atelier/Dropzone'
import { Button } from '../components/ui/Button'
import { ErrorState, Loading } from '../components/ui/States'
import { useToast } from '../components/ui/Toast'
import { texts } from '../content/texts'
import { api, ApiError } from '../lib/api'
import { useAsync } from '../lib/hooks'
import type { MergeAnalysis, MergeCandidate, MergeDecision, MergeResult } from '../lib/types'
import { gsap, useGSAP } from '../motion/gsap'
import { d, ease, prefersReducedMotion } from '../motion/tokens'

const DOCX = '.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document'

function defaultDecision(c: MergeCandidate): MergeDecision {
  const first = c.propositions.findIndex((p) => !p.incomplet)
  return c.sur && first >= 0 ? { choix: 'proposition', proposition: first + 1 } : { choix: 'ignorer' }
}

function CandidateCard({ c, decision, onChange }: { c: MergeCandidate; decision: MergeDecision; onChange: (d: MergeDecision) => void }) {
  const chosen = decision.choix === 'proposition' ? c.propositions[(decision.proposition ?? 1) - 1] : null
  const preview = decision.choix === 'ignorer' ? c.nombre : decision.choix === 'code' ? `<<${(decision.code ?? '').replace(/[<>]/g, '')}>>` : chosen?.merge_code ?? c.nombre
  return (
    <li data-cand className={`rounded-[var(--radius-card)] border-[2.5px] border-fg p-5 transition-colors ${decision.choix === 'ignorer' ? 'bg-card-2' : 'bg-card shadow-[4px_4px_0_0_var(--color-fg)]'}`}>
      <div className="flex flex-wrap items-center gap-2 text-xs font-bold">
        <span className={`rounded-full border-2 border-fg px-2.5 py-0.5 ${c.sur ? 'bg-mint-400' : 'bg-sun-400'}`}>{c.sur ? texts.merge.safe : texts.merge.toConfirm}</span>
        <span className="rounded-full border-2 border-fg bg-canvas px-2.5 py-0.5">{c.type}</span>
        <span className="text-fg-3">Texte {c.texte_id}{c.titre ? ` · ${c.titre}` : ''}</span>
      </div>
      <p className="mt-3 text-lg leading-relaxed">
        <span className="text-fg-2">{c.avant}</span>
        <mark className={`mx-0.5 rounded-lg border-2 border-fg px-1.5 font-display font-semibold ${decision.choix === 'ignorer' ? 'bg-card-3' : 'bg-sun-400'}`}>{preview}</mark>
        <span className="text-fg-2">{c.apres}</span>
      </p>
      {c.remarques.length > 0 && (
        <ul className="mt-2 text-sm font-semibold text-warning">{c.remarques.map((r) => <li key={r}>⚠ {r}</li>)}</ul>
      )}
      <fieldset className="mt-4">
        <legend className="sr-only">Merge code pour « {c.avant}{c.nombre}{c.apres} »</legend>
        <div className="flex flex-wrap gap-2">
          {c.propositions.map((p, i) => {
            const active = decision.choix === 'proposition' && (decision.proposition ?? 1) === i + 1
            return (
              <button key={p.code} type="button" disabled={p.incomplet} aria-pressed={active}
                onClick={() => onChange({ choix: 'proposition', proposition: i + 1 })}
                title={p.statut}
                className={`flex flex-col items-start rounded-xl border-2 border-fg px-3 py-1.5 text-left text-sm transition-[transform,box-shadow] disabled:opacity-40 ${active ? 'bg-magic-500 text-white shadow-[2px_2px_0_0_var(--color-fg)]' : 'bg-card hover:-translate-y-0.5'}`}>
                <span className="font-mono font-bold">{p.merge_code}</span>
                <span className={`text-xs font-semibold ${active ? 'text-white/85' : 'text-fg-2'}`}>{p.libelle} · {p.valeur_excel ?? '—'} an{(p.valeur_excel ?? 0) > 1 ? 's' : ''}</span>
              </button>
            )
          })}
          <button type="button" aria-pressed={decision.choix === 'ignorer'} onClick={() => onChange({ choix: 'ignorer' })}
            className={`inline-flex items-center gap-1.5 rounded-xl border-2 px-3 py-1.5 text-sm font-bold ${decision.choix === 'ignorer' ? 'border-fg bg-fg text-canvas' : 'border-fg/30 hover:border-fg'}`}>
            <X size={14} aria-hidden="true" />{texts.merge.skip}
          </button>
          <label className={`inline-flex items-center gap-1.5 rounded-xl border-2 px-2 py-1 text-sm font-bold ${decision.choix === 'code' ? 'border-fg bg-sun-400' : 'border-fg/30'}`}>
            <span className="pl-1">{texts.merge.custom}</span>
            <input value={decision.choix === 'code' ? decision.code ?? '' : ''} placeholder="XPSDG_…"
              onChange={(e) => onChange(e.target.value ? { choix: 'code', code: e.target.value } : defaultDecision(c))}
              className="w-32 rounded-lg border-2 border-fg bg-card px-2 py-0.5 font-mono text-sm focus:outline-none" />
          </label>
        </div>
      </fieldset>
    </li>
  )
}

export default function MergeCodes() {
  const toast = useToast()
  const root = useRef<HTMLDivElement>(null)
  const refInput = useRef<HTMLInputElement>(null)
  const ref = useAsync(() => api.merge.referentiel(), [])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [analysis, setAnalysis] = useState<MergeAnalysis | null>(null)
  const [decisions, setDecisions] = useState<MergeDecision[]>([])
  const [applying, setApplying] = useState(false)
  const [result, setResult] = useState<MergeResult | null>(null)

  useGSAP(() => {
    if (prefersReducedMotion()) return
    gsap.from('[data-enter]', { y: 30, opacity: 0, stagger: 0.08, duration: d('slow'), ease: ease.out })
    gsap.from('[data-cand]', { y: 24, opacity: 0, rotation: () => gsap.utils.random(-2, 2), stagger: 0.05, duration: d('base'), ease: 'back.out(1.6)' })
  }, { scope: root, dependencies: [analysis?.id, !!result] })

  const load = async (loader: Promise<MergeAnalysis>) => {
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const a = await loader
      setAnalysis(a)
      setDecisions(a.candidats.map(defaultDecision))
      ref.reload()
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(String(e)))
    } finally {
      setBusy(false)
    }
  }

  const uploadRef = async (file: File) => {
    try {
      await api.merge.uploadReferentiel(file)
      ref.reload()
      toast('success', texts.merge.refTitle, file.name)
    } catch (e) {
      toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
    }
  }

  const apply = async () => {
    if (!analysis) return
    setApplying(true)
    try {
      const r = await api.merge.apply(analysis.id, decisions)
      setResult(r)
      window.dispatchEvent(new Event('grimoire:shower'))
      toast('success', texts.merge.done(r.inseres))
    } catch (e) {
      toast('error', e instanceof ApiError ? e.message : texts.errors.generic, e instanceof ApiError ? e.hint : undefined)
    } finally {
      setApplying(false)
    }
  }

  const count = decisions.filter((x) => x.choix !== 'ignorer').length
  const texteCount = useMemo(() => new Set(analysis?.candidats.map((c) => c.texte_id)).size, [analysis])
  const r = ref.data

  return (
    <div ref={root} className="mx-auto w-[min(100%-2rem,82rem)] pt-10 sm:pt-14">
      <header data-enter className="max-w-3xl">
        <p className="eyebrow"><Tags size={13} aria-hidden="true" />{texts.merge.eyebrow}</p>
        <h1 className="mt-4 text-[clamp(2.4rem,6vw,4.5rem)] font-bold">{texts.merge.title}</h1>
        <p className="mt-4 text-lg font-semibold text-fg-2">{texts.merge.lead}</p>
      </header>

      {/* Référentiel */}
      <section data-enter className="glass mt-10 flex flex-wrap items-center gap-4 rounded-[var(--radius-card)] p-5">
        <span className={`grid size-12 place-items-center rounded-2xl border-[2.5px] border-fg ${r?.present ? 'bg-mint-400' : 'bg-sun-400'}`}>
          {r?.present ? <Check size={24} aria-hidden="true" /> : <Upload size={22} aria-hidden="true" />}
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-display text-xl font-semibold">{texts.merge.refTitle}</p>
          {ref.loading && !r ? <Loading compact /> : r?.present ? (
            <p className="text-sm font-semibold text-fg-2">
              {r.meta?.filename} · {texts.merge.refLoaded(r.personnes ?? 0, r.annee ?? new Date().getFullYear())}
              {(r.nb_anomalies ?? 0) > 0 && <span className="text-warning"> · {texts.merge.anomalies(r.nb_anomalies ?? 0)}</span>}
            </p>
          ) : (
            <p className="text-sm font-semibold text-fg-2">{texts.merge.refMissing}</p>
          )}
        </div>
        <Button size="sm" onClick={() => refInput.current?.click()} icon={<Upload size={16} />}>{r?.present ? texts.merge.refReplace : texts.merge.refUpload}</Button>
        <input ref={refInput} type="file" accept=".xlsx,.xlsm" className="sr-only" tabIndex={-1}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) void uploadRef(f); e.target.value = '' }} />
        {r?.present && (r.anomalies?.length ?? 0) > 0 && (
          <details className="w-full text-sm">
            <summary className="font-bold text-warning">{texts.merge.anomalies(r.nb_anomalies ?? 0)}</summary>
            <ul className="mt-2 list-disc space-y-0.5 pl-5 font-semibold text-fg-2">{r.anomalies?.map((a) => <li key={a}>{a}</li>)}</ul>
          </details>
        )}
      </section>

      {!analysis && (
        <div data-enter className="mt-8 flex flex-col gap-4">
          <Dropzone onFile={(f) => load(api.merge.upload(f))} busy={busy} accept={DOCX}
            title={texts.merge.drop} body={texts.merge.dropHint} activeTitle={texts.rfi.dropActive} busyTitle={texts.merge.analyzing} />
          <div><Button onClick={() => load(api.merge.demo())} disabled={busy} icon={<Sparkles size={18} />}>{texts.merge.demo}</Button></div>
          {error && <ErrorState error={error} />}
        </div>
      )}

      {analysis && (
        <>
          <section data-enter className="mt-8 flex flex-wrap items-center gap-3">
            <span className="grid size-11 place-items-center rounded-2xl border-[2.5px] border-fg bg-bubble-400"><FileText size={22} aria-hidden="true" /></span>
            <div className="min-w-0 flex-1">
              <p className="truncate font-display text-xl font-semibold">{analysis.filename}</p>
              <p className="text-sm font-semibold text-fg-2">{texts.merge.texts(analysis.textes)} · {texts.merge.passages(analysis.candidats.length)} · {texteCount} texte(s) concerné(s)</p>
            </div>
            {!result && analysis.candidats.length > 0 && (
              <Button size="sm" onClick={() => setDecisions(analysis.candidats.map(defaultDecision))} icon={<Check size={16} />}>{texts.merge.acceptSafe}</Button>
            )}
            <Button variant="ghost" size="sm" onClick={() => { setAnalysis(null); setResult(null) }} icon={<RotateCcw size={16} />}>{texts.merge.restart}</Button>
          </section>

          {analysis.candidats.length === 0 ? (
            <p className="glass mt-6 rounded-[var(--radius-card)] p-6 font-semibold">{texts.merge.none}</p>
          ) : (
            <ul className="mt-6 flex flex-col gap-4">
              {analysis.candidats.map((c, i) => (
                <CandidateCard key={c.index} c={c} decision={decisions[i] ?? defaultDecision(c)}
                  onChange={(next) => setDecisions((all) => all.map((x, k) => (k === i ? next : x)))} />
              ))}
            </ul>
          )}

          {analysis.signalements.length > 0 && (
            <section className="mt-6 rounded-[var(--radius-card)] border-[2.5px] border-dashed border-warning bg-sun-400/15 p-5">
              <h2 className="flex items-center gap-2 text-xl"><TriangleAlert size={20} className="text-warning" aria-hidden="true" />{texts.merge.warnings}</h2>
              <ul className="mt-2 space-y-1 text-sm font-semibold text-fg-2">
                {analysis.signalements.map((s, i) => <li key={i}>Texte {s.texte_id} — {s.motif} : « {s.extrait} »</li>)}
              </ul>
            </section>
          )}

          <section data-enter className="mt-8 rounded-[var(--radius-card)] border-[2.5px] border-fg bg-bubble-400 p-6 shadow-[var(--shadow-pop-lg)]">
            {!result ? (
              <div className="flex flex-wrap items-center justify-between gap-4">
                <p className="font-display text-xl font-semibold">{texts.merge.zero}</p>
                <Button size="lg" onClick={apply} loading={applying} disabled={count === 0} icon={<Sparkles size={20} />} className="!bg-card">
                  {applying ? texts.merge.applying : texts.merge.apply(count)}
                </Button>
              </div>
            ) : (
              <div className="flex flex-col gap-4">
                <div className="flex flex-wrap items-center gap-4">
                  <span className="grid size-14 place-items-center rounded-full border-[2.5px] border-fg bg-mint-400"><Check size={28} aria-hidden="true" /></span>
                  <p className="flex-1 font-display text-2xl font-semibold">{texts.merge.done(result.inseres)}</p>
                  {[{ href: result.document_url, label: texts.merge.downloadDoc }, { href: result.rapport_url, label: texts.merge.downloadReport }].map((l) => (
                    <a key={l.href} href={l.href} className="inline-flex h-12 items-center gap-2 rounded-full border-[2.5px] border-fg bg-card px-5 font-display font-semibold shadow-[3px_3px_0_0_var(--color-fg)] transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow-[5px_5px_0_0_var(--color-fg)]">
                      <Download size={18} aria-hidden="true" />{l.label}
                    </a>
                  ))}
                </div>
                <p className="flex flex-wrap gap-2 text-sm font-bold">
                  {Object.entries(result.statuts).map(([k, v]) => <span key={k} className="rounded-full border-2 border-fg bg-card px-2.5 py-0.5">{v} · {k}</span>)}
                </p>
                {result.journal && (
                  <details className="rounded-xl border-2 border-fg bg-card p-3">
                    <summary className="font-bold">{texts.run.logs}</summary>
                    <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap font-mono text-xs">{result.journal}</pre>
                  </details>
                )}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}
