/**
 * API & moteur : chaque appel Qvidian mesuré (latence p50 / p95, erreurs, cache, relances, attente du limiteur),
 * synchronisation complète ou incrémentale, modèles du moteur sémantique (installation explicite, 100 % local).
 */
import { useCallback, useEffect, useState } from 'react'
import { CheckCircle2, Cpu, Download, Gauge, RefreshCw, RotateCcw, Zap } from 'lucide-react'
import { Bar, Kpi } from '../../../components/qvidian/Bits'
import { HistoryPanel } from '../../../components/qvidian/HistoryPanel'
import { Button } from '../../../components/ui/Button'
import { texts } from '../../../content/texts'
import { api } from '../../../lib/api'
import type { QvidianApiStats, QvidianEngineStatus } from '../../../lib/types'
import { useQvidian } from '../context'

const Q = texts.qvidian

export function ApiView() {
  const { status, sync, fail } = useQvidian()
  const [stats, setStats] = useState<QvidianApiStats | null>(null)
  const [engine, setEngine] = useState<QvidianEngineStatus | null>(null)
  const load = useCallback(async () => {
    try {
      const [s, e] = await Promise.all([api.qvidian.apiStats(), api.qvidian.engine()])
      setStats(s); setEngine(e)
    } catch (e) { fail(e) }
  }, [fail])
  useEffect(() => { void load() }, [load, status?.sync.running])
  // Téléchargement ou indexation en cours : on suit l'avancement
  const busy = engine?.models.some((m) => m.download?.running) || engine?.building?.running
  useEffect(() => {
    if (!busy) return
    const t = window.setInterval(() => void load(), 1500)
    return () => window.clearInterval(t)
  }, [busy, load])
  const tel = stats?.telemetry
  const maxCalls = Math.max(1, ...(tel?.operations ?? []).map((o) => o.calls))
  const install = async (id: string) => {
    try { await api.qvidian.downloadModel(id); void load() } catch (e) { fail(e) }
  }
  return (
    <div className="flex flex-col gap-5">
      <header data-enter>
        <h1 className="text-[clamp(1.8rem,3.6vw,2.8rem)] font-bold leading-none">{Q.apiTitle}</h1>
        <p className="mt-2 max-w-3xl text-sm font-semibold text-fg-2">{Q.apiLead}</p>
      </header>

      <section data-enter className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Kpi label={Q.statCalls} value={tel?.calls ?? 0} />
        <Kpi label={Q.statP50} value={`${tel?.p50_ms ?? 0} ms`} />
        <Kpi label={Q.statP95} value={`${tel?.p95_ms ?? 0} ms`} />
        <Kpi label={Q.statCache} value={`${Math.round((tel?.cache_rate ?? 0) * 100)} %`} />
        <Kpi label={Q.statErrors} value={`${Math.round((tel?.error_rate ?? 0) * 100)} %`} />
        <Kpi label={Q.statWait} value={`${stats?.limiter_wait_s ?? 0} s`} />
      </section>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <section data-enter className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-5">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="flex items-center gap-2 text-lg"><Gauge size={17} aria-hidden="true" />{Q.opsTitle}</h2>
            <Button size="sm" variant="ghost" className="ml-auto" onClick={async () => setStats(await api.qvidian.resetStats())} icon={<RotateCcw size={14} />}>{Q.resetStats}</Button>
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[36rem] text-sm">
              <thead className="text-left text-xs uppercase tracking-wider text-fg-3">
                <tr><th className="p-1.5">Opération</th><th className="p-1.5">Appels</th><th className="p-1.5">p50</th><th className="p-1.5">p95</th><th className="p-1.5">Cache</th><th className="p-1.5">Relances</th><th className="p-1.5">Erreurs</th><th className="p-1.5">Ko</th></tr>
              </thead>
              <tbody>
                {(tel?.operations ?? []).map((o) => (
                  <tr key={o.op} className="border-t border-fg/10">
                    <td className="p-1.5"><span className="font-mono text-xs font-bold">{o.op}</span><Bar value={o.calls / maxCalls} tone="bg-magic-400" /></td>
                    <td className="p-1.5 font-bold tabular-nums">{o.calls}</td>
                    <td className="p-1.5 tabular-nums">{o.p50_ms}</td>
                    <td className={`p-1.5 tabular-nums ${o.p95_ms > 2000 ? 'font-bold text-warning' : ''}`}>{o.p95_ms}</td>
                    <td className="p-1.5 tabular-nums">{o.cached}</td>
                    <td className="p-1.5 tabular-nums">{o.retries}</td>
                    <td className={`p-1.5 tabular-nums ${o.errors ? 'font-bold text-danger' : ''}`}>{o.errors}</td>
                    <td className="p-1.5 tabular-nums">{o.kb_in}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <details className="mt-4">
            <summary className="cursor-pointer text-sm font-bold">{Q.recentTitle} ({tel?.recent.length ?? 0})</summary>
            <ul className="mt-2 max-h-64 overflow-y-auto font-mono text-xs" data-lenis-prevent>
              {(tel?.recent ?? []).map((r, i) => (
                <li key={i} className={`flex gap-3 border-b border-fg/5 py-0.5 ${r.ok ? '' : 'text-danger'}`}>
                  <span className="text-fg-3">{r.at}</span><span className="flex-1 truncate">{r.op}</span>
                  <span>{r.cached ? 'cache' : `${r.ms} ms`}</span>{r.retries ? <span>↻{r.retries}</span> : null}{r.code && <span>{r.code}</span>}
                </li>
              ))}
            </ul>
          </details>
        </section>

        <div className="flex flex-col gap-5">
          <section data-enter className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-5">
            <h2 className="flex items-center gap-2 text-lg"><RefreshCw size={17} aria-hidden="true" />{Q.syncTitle}</h2>
            <p className="mt-1 text-xs font-semibold text-fg-2">{Q.syncLead}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="sm" variant="primary" onClick={() => sync('delta')} disabled={status?.sync.running} icon={<Zap size={14} />}>{Q.syncDelta}</Button>
              <Button size="sm" onClick={() => sync('full')} disabled={status?.sync.running} icon={<RefreshCw size={14} />}>{Q.syncFull}</Button>
            </div>
            <p className="mt-2 text-xs font-bold text-fg-2">
              {stats?.delta_supported === true ? Q.deltaYes : stats?.delta_supported === false ? Q.deltaNo : Q.deltaUnknown}
            </p>
            {stats?.last_sync && (
              <p className="mt-1 text-xs font-semibold text-fg-3">
                {Q.lastSyncCard(stats.last_sync.mode ?? 'full', stats.last_sync.seconds ?? 0)} · {stats.last_sync.contents} contenus
                {stats.last_sync.mode === 'delta' ? ` · ${stats.last_sync.changed} modifiés · ${stats.last_sync.removed} supprimés` : ` · ${stats.last_sync.folders} dossiers · ${stats.last_sync.workers} en parallèle`}
              </p>
            )}
            {status?.sync.running && <p className="mt-1 text-xs font-bold" aria-live="polite">{status.sync.message}</p>}
          </section>
          <section data-enter className="rounded-[var(--radius-card)] border-2 border-fg bg-card p-5">
            <h2 className="text-lg">{Q.settingsTitle}</h2>
            <dl className="mt-2 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-sm">
              {stats && Object.entries({
                QVIDIAN_CONCURRENCY: stats.settings.concurrency, QVIDIAN_MAX_CALLS_PER_SECOND: stats.settings.max_calls_per_second,
                QVIDIAN_CACHE_SECONDS: stats.settings.cache_seconds, QVIDIAN_KEEPALIVE_MINUTES: stats.settings.keepalive_minutes,
                MERLIN_SEARCH_ENCODER: stats.settings.search_encoder, MERLIN_SEARCH_RERANKER: stats.settings.search_reranker ? 'on' : 'off',
              }).map(([k, v]) => <div key={k} className="contents"><dt className="font-mono text-xs font-bold text-fg-3">{k}</dt><dd className="font-semibold">{String(v)}</dd></div>)}
            </dl>
          </section>
        </div>
      </div>

      <div data-enter><HistoryPanel /></div>

      <section data-enter className="rounded-[var(--radius-card)] border-[2.5px] border-fg bg-card p-5">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="flex items-center gap-2 text-xl"><Cpu size={18} aria-hidden="true" />{Q.engineTitle}</h2>
          <Button size="sm" className="ml-auto" onClick={async () => { try { setEngine(await api.qvidian.rebuild()) } catch (e) { fail(e) } }} icon={<RefreshCw size={14} />}>{Q.rebuild}</Button>
        </div>
        <p className="mt-1 max-w-3xl text-sm font-semibold text-fg-2">{Q.engineLead}</p>
        <p className="mt-1 text-xs font-semibold text-fg-3">{Q.measured}</p>
        {engine && !engine.neural_runtime && <p className="mt-2 text-sm font-bold text-warning">{Q.noRuntime}</p>}
        <p className="mt-2 text-sm font-bold">
          {engine?.engine?.encoder ? Q.engineNeural(engine.engine.encoder, engine.engine.reranker) : Q.engineLexical}
          {engine?.engine ? ` · ${engine.engine.documents} contenus` : ''}
          {engine?.building?.running ? ` · ${Q.indexing} ${engine.building.message} ${engine.building.done}/${engine.building.total}` : ''}
          {engine?.building?.error ? ` · ${engine.building.error}` : ''}
        </p>
        <ul className="mt-4 grid gap-3 md:grid-cols-3">
          {(engine?.models ?? []).map((m) => {
            const dl = m.download
            const pct = dl?.total ? dl.done / dl.total : 0
            const recommended = m.id === 'e5-small' || m.id === 'rerank-mminilm'
            return (
              <li key={m.id} className={`flex flex-col gap-2 rounded-2xl border-2 p-4 ${m.installed ? 'border-fg bg-mint-400/15' : 'border-fg/30'}`}>
                <p className="flex flex-wrap items-center gap-2 font-display font-semibold">
                  {m.label}{recommended && <span className="rounded-full bg-sun-400 px-2 text-[0.65rem] font-bold">{Q.recommended}</span>}
                </p>
                <p className="text-xs font-semibold text-fg-2">{m.kind === 'encoder' ? 'Encodeur (sens)' : 'Reranker (lecture fine)'} · {m.size_mb} Mo · {m.license}</p>
                <p className="text-xs font-semibold text-fg-3">{m.note}</p>
                {m.error && <p className="text-xs font-bold text-danger">{m.error}</p>}
                {dl?.error && <p className="text-xs font-bold text-danger">{dl.error}</p>}
                {dl?.running ? (
                  <div aria-live="polite"><p className="text-xs font-bold">{Q.downloading} {Math.round(pct * 100)} %</p><Bar value={pct} tone="bg-magic-400" /></div>
                ) : m.installed ? (
                  <p className="inline-flex items-center gap-1 text-sm font-bold text-mint-300"><CheckCircle2 size={15} aria-hidden="true" />{m.active ? Q.active : Q.installed}</p>
                ) : (
                  <Button size="sm" onClick={() => install(m.id)} disabled={!engine?.neural_runtime} icon={<Download size={14} />}>{Q.install(m.size_mb)}</Button>
                )}
              </li>
            )
          })}
        </ul>
      </section>
    </div>
  )
}
