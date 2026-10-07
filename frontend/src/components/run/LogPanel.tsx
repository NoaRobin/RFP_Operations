import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { texts } from '../../content/texts'
import { gsap } from '../../motion/gsap'
import { d, ease } from '../../motion/tokens'
import type { LogLine } from './useRunStream'

const LEVEL = {
  debug: 'text-haze',
  info: 'text-mist',
  success: 'text-success',
  warning: 'text-warning',
  error: 'text-danger',
} as Record<string, string>

const TAG = { debug: 'DBG', info: 'INF', success: ' OK', warning: 'WRN', error: 'ERR' } as Record<string, string>

export function LogPanel({ logs, live }: { logs: LogLine[]; live: boolean }) {
  const [debug, setDebug] = useState(false)
  const [follow, setFollow] = useState(true)
  const box = useRef<HTMLDivElement>(null)
  const lastId = useRef(0)
  const shown = debug ? logs : logs.filter((l) => l.level !== 'debug')

  useLayoutEffect(() => {
    const el = box.current
    if (!el) return
    const fresh = Array.from(el.querySelectorAll<HTMLElement>('[data-log]')).filter((n) => Number(n.dataset.log) > lastId.current)
    if (fresh.length && fresh.length < 20) gsap.from(fresh, { opacity: 0, x: -8, duration: d('base'), ease: ease.out, stagger: 0.02 })
    lastId.current = logs.length ? logs[logs.length - 1].id : 0
    if (follow) el.scrollTop = el.scrollHeight
  }, [logs, follow, debug])

  useEffect(() => {
    const el = box.current
    if (!el) return
    const onScroll = () => setFollow(el.scrollHeight - el.scrollTop - el.clientHeight < 40)
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <section aria-labelledby="logs-title" className="glass flex flex-col rounded-[var(--radius-card)]">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b hairline px-5 py-3">
        <h2 id="logs-title" className="flex items-center gap-2 font-mono text-sm uppercase tracking-[0.2em] text-gold-300">
          {live && <span className="size-2 animate-pulse rounded-full bg-arcane-400" aria-hidden="true" />}
          {texts.run.logs}
        </h2>
        <div className="flex items-center gap-2 text-xs">
          {!follow && (
            <button onClick={() => setFollow(true)} className="rounded-full border border-line-strong px-3 py-1 text-mist hover:text-parchment">
              {texts.run.followLogs}
            </button>
          )}
          <button onClick={() => setDebug((v) => !v)} aria-pressed={debug} className="rounded-full border border-line-strong px-3 py-1 text-mist hover:text-parchment">
            {debug ? texts.run.hideDebug : texts.run.showDebug}
          </button>
        </div>
      </header>
      <div
        ref={box}
        role="log"
        aria-live="polite"
        aria-relevant="additions"
        tabIndex={0}
        data-lenis-prevent
        className="h-80 overflow-y-auto px-5 py-4 font-mono text-[0.8rem] leading-6"
      >
        {shown.length === 0 && <p className="text-haze">{texts.loading[0]}</p>}
        {shown.map((line) => (
          <div key={line.id} data-log={line.id} className={`flex gap-3 ${LEVEL[line.level] ?? 'text-mist'}`}>
            <span className="shrink-0 text-haze/70 tabular-nums">{line.ts.slice(11, 19)}</span>
            <span className="shrink-0 opacity-80">{TAG[line.level] ?? 'INF'}</span>
            <span className="whitespace-pre-wrap break-words">{line.message}</span>
          </div>
        ))}
      </div>
    </section>
  )
}
