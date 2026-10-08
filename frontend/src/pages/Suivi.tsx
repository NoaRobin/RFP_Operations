/** Suivi d'activité : le module tryv2, servi tel quel sous /suivi, encadré façon Grimoire. */
import { useEffect, useState } from 'react'
import { Activity, ExternalLink } from 'lucide-react'
import { EmptyState, Loading } from '../components/ui/States'
import { texts } from '../content/texts'

export default function Suivi() {
  const [state, setState] = useState<'loading' | 'ok' | 'down'>('loading')

  useEffect(() => {
    let alive = true
    fetch('/suivi/', { method: 'GET' })
      .then((r) => alive && setState(r.ok ? 'ok' : 'down'))
      .catch(() => alive && setState('down'))
    return () => {
      alive = false
    }
  }, [])

  return (
    <div className="mx-auto w-[min(100%-2rem,90rem)] pt-8 sm:pt-10">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-3xl">
          <p className="eyebrow"><Activity size={13} aria-hidden="true" />{texts.suivi.eyebrow}</p>
          <h1 className="mt-3 text-[clamp(2rem,4.5vw,3.5rem)] font-bold">{texts.suivi.title}</h1>
          <p className="mt-2 font-semibold text-fg-2">{texts.suivi.lead}</p>
        </div>
        <a href="/suivi/" target="_blank" rel="noopener"
          className="inline-flex h-11 items-center gap-2 rounded-full border-[2.5px] border-fg bg-card px-5 font-display font-semibold shadow-[3px_3px_0_0_var(--color-fg)] transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow-[5px_5px_0_0_var(--color-fg)]">
          <ExternalLink size={18} aria-hidden="true" />{texts.suivi.open}
        </a>
      </header>
      <div className="mt-6 overflow-hidden rounded-[var(--radius-card)] border-[2.5px] border-fg bg-card shadow-[var(--shadow-pop-lg)]">
        {state === 'loading' && <Loading />}
        {state === 'down' && <EmptyState title={texts.suivi.unavailable} body={texts.suivi.unavailableHint} />}
        {state === 'ok' && <iframe src="/suivi/" title={texts.suivi.title} className="block h-[calc(100dvh-14rem)] min-h-[40rem] w-full bg-white" />}
      </div>
    </div>
  )
}
