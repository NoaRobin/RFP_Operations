import { useMemo, useState } from 'react'
import { GripVertical, Search, TriangleAlert, Wand2 } from 'lucide-react'
import { texts } from '../../content/texts'
import type { Extraction } from '../../lib/types'
import { gsap } from '../../motion/gsap'
import { d, ease } from '../../motion/tokens'
import { DRAG_TYPE } from './SheetGrid'

const assignLabel = (target: string) => (target.startsWith('#') ? texts.atelier.assignToRow(target) : texts.atelier.assignTo(target))

function normalize(text: string) {
  return text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
}

export function ExtractionPanel({
  extractions, keyType, selectedColumn, usedIds, onAssign,
}: { extractions: Extraction[]; keyType: string; selectedColumn: string | null; usedIds: Set<string>; onAssign: (id: string) => void }) {
  const [query, setQuery] = useState('')
  const groups = useMemo(() => {
    const q = normalize(query)
    const list = extractions
      .filter((e) => e.healthy && e.key === keyType)
      .filter((e) => !q || normalize([e.label, e.source, ...e.synonyms].join(' ')).includes(q))
    const map = new Map<string, Extraction[]>()
    list.forEach((e) => map.set(e.group, [...(map.get(e.group) ?? []), e]))
    return [...map.entries()]
  }, [extractions, keyType, query])

  return (
    <aside aria-labelledby="catalog-title" className="glass flex max-h-[44rem] flex-col rounded-[var(--radius-card)]">
      <header className="border-b hairline p-5">
        <h2 id="catalog-title" className="text-xl">{texts.atelier.catalog}</h2>
        <p className="mt-1 text-xs text-fg-3">{texts.atelier.catalogHelp}</p>
        <div className="relative mt-4">
          <label htmlFor="extraction-search" className="sr-only">{texts.atelier.catalogSearch}</label>
          <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-3" aria-hidden="true" />
          <input id="extraction-search" type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={texts.atelier.catalogSearch}
            className="h-10 w-full rounded-full border border-line-strong bg-field/60 pl-9 pr-3 text-sm placeholder:text-fg-3 focus:border-mint-400 focus:outline-none" />
        </div>
      </header>
      <div className="flex-1 overflow-y-auto p-3" data-lenis-prevent>
        {groups.map(([group, items]) => (
          <section key={group} className="mb-4">
            <h3 className="px-2 pb-2 eyebrow !text-[0.65rem]">{group}</h3>
            <ul className="flex flex-col gap-1.5">
              {items.map((e) => (
                <li key={e.id}>
                  <div
                    draggable
                    onDragStart={(ev) => {
                      ev.dataTransfer.setData(DRAG_TYPE, e.id)
                      ev.dataTransfer.effectAllowed = 'copy'
                      gsap.to(ev.currentTarget, { scale: 0.97, opacity: 0.7, duration: d('fast') })
                    }}
                    onDragEnd={(ev) => gsap.to(ev.currentTarget, { scale: 1, opacity: 1, duration: d('base'), ease: ease.spring })}
                    className={`group flex cursor-grab items-start gap-2 rounded-xl border p-3 transition-colors active:cursor-grabbing ${
                      usedIds.has(e.id) ? 'border-sun-400/40 bg-sun-400/[0.06]' : 'border-line hover:border-magic-400/50 hover:bg-fg/[0.04]'}`}
                  >
                    <GripVertical size={16} className="mt-0.5 shrink-0 text-fg-3 group-hover:text-fg-2" aria-hidden="true" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-fg">{e.label}</p>
                      <p className="truncate font-mono text-[0.68rem] text-fg-3">{e.source}</p>
                      {e.caution && (
                        <p className="mt-1 flex items-center gap-1 text-[0.68rem] text-warning" title={e.caution}>
                          <TriangleAlert size={11} aria-hidden="true" />{texts.atelier.caution}
                        </p>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => onAssign(e.id)}
                      disabled={!selectedColumn}
                      title={selectedColumn ? assignLabel(selectedColumn) : texts.atelier.selectColumnFirst}
                      aria-label={selectedColumn ? `${assignLabel(selectedColumn)} : ${e.label}` : `${texts.atelier.assign} ${e.label} — ${texts.atelier.selectColumnFirst}`}
                      className="shrink-0 rounded-full p-1.5 text-sun-300 transition-colors hover:bg-sun-400/15 disabled:text-fg-3 disabled:hover:bg-transparent"
                    >
                      <Wand2 size={16} />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ))}
        {groups.length === 0 && <p className="p-4 text-sm text-fg-3">{texts.library.emptySearch.title}</p>}
      </div>
    </aside>
  )
}
