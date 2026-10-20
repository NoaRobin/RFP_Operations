/**
 * Parts détectées dans le document (plusieurs ISIN) : chaque question lit la part de sa ligne, de sa colonne
 * ou de sa section. Un clic choisit la part principale (questions générales du document).
 */
import { Layers } from 'lucide-react'
import { texts } from '../../content/texts'
import type { DocumentShare } from '../../lib/types'

export function SharesPanel({ shares, isin, onPick }: { shares: DocumentShare[]; isin: string | null; onPick: (pid: string, isin: string) => void }) {
  const listed = shares.filter((s) => s.questions > 0)
  return (
    <section aria-labelledby="shares-title" className="rounded-2xl border-[2.5px] border-fg bg-mint-400/15 p-4">
      <h3 id="shares-title" className="flex items-center gap-2 font-display text-lg font-semibold">
        <Layers size={18} aria-hidden="true" />{texts.rfi.sharesTitle(listed.length)}
      </h3>
      <p className="mt-1 text-sm font-semibold text-fg-2">{texts.rfi.sharesLead}</p>
      <ul className="mt-3 flex flex-wrap gap-2">
        {listed.map((s) => {
          const active = s.isin === isin
          const label = s.share_name ?? s.isin
          return (
            <li key={s.isin}>
              <button type="button" disabled={!s.known || !s.pid} aria-pressed={active}
                onClick={() => s.pid && onPick(s.pid, s.isin)}
                title={s.known ? texts.rfi.shareUse : texts.rfi.shareUnknown}
                className={`flex flex-col items-start rounded-2xl border-[2.5px] border-fg px-3 py-1.5 text-left transition-[transform,box-shadow] motion-safe:hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-70 ${
                  active ? 'bg-sun-400 shadow-[3px_3px_0_0_var(--color-fg)]' : 'bg-card hover:shadow-[3px_3px_0_0_var(--color-fg)]'}`}>
                <span className="font-display text-sm font-semibold">{label}</span>
                <span className="font-mono text-[0.7rem] font-semibold text-fg-2">
                  {s.isin} · {texts.rfi.shareQuestions(s.questions)}{s.known ? '' : ` · ${texts.rfi.shareUnknown}`}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
