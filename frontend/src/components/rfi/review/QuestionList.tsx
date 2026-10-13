/** Liste compacte des questions, regroupées par section, avec leur état. */
import { texts } from '../../../content/texts'
import type { RfiQuestion } from '../../../lib/types'
import { STATE_DOT, type ReviewState } from './state'

export function QuestionList({ questions, states, selected, onSelect }: {
  questions: RfiQuestion[]; states: Record<string, ReviewState>; selected: string | null; onSelect: (id: string) => void
}) {
  if (questions.length === 0) return <p className="p-3 text-sm font-semibold text-fg-2">{texts.review.noQuestion}</p>
  const groups: { section: string; items: RfiQuestion[] }[] = []
  for (const q of questions) {
    const raw = q.layout === 'list' ? q.context || '' : q.location.split('!')[0]
    const section = /^[\d.\s]+$/.test(raw) ? '' : raw  // un numéro de ligne n'est pas une section
    const last = groups[groups.length - 1]
    if (last && last.section === section) last.items.push(q)
    else groups.push({ section, items: [q] })
  }
  return (
    <div className="flex flex-col gap-3">
      {groups.map((g, i) => (
        <section key={`${g.section}-${i}`}>
          {g.section && <h4 className="mb-1 text-[0.65rem] font-bold uppercase tracking-wider text-fg-3">{g.section}</h4>}
          <ul className="flex flex-col gap-1">
            {g.items.map((q) => (
              <li key={q.id}>
                <button data-q={q.id} onClick={() => onSelect(q.id)} aria-current={selected === q.id}
                  className={`flex w-full items-start gap-2 rounded-xl border-2 px-2.5 py-1.5 text-left text-sm transition-[transform,box-shadow] ${selected === q.id ? 'border-fg bg-card shadow-[3px_3px_0_0_var(--color-fg)]' : 'border-transparent hover:border-fg/30'}`}>
                  <span className={`mt-1 size-2.5 shrink-0 rounded-full border-2 border-fg ${STATE_DOT[states[q.id] ?? 'none']}`} aria-hidden="true" />
                  <span className="min-w-0 flex-1">
                    <span className="line-clamp-2 font-semibold">{q.question}</span>
                    {q.answer && <span className="block truncate text-xs font-bold text-fg-2">{q.answer}</span>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}
