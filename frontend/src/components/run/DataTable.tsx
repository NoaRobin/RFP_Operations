import { texts } from '../../content/texts'
import { formatNumber } from '../../lib/format'

function cell(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'number') return formatNumber(value, Math.abs(value) >= 1000 ? 0 : 4)
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}/.test(value)) return new Date(value).toLocaleDateString('fr-FR')
  return String(value)
}

export function DataTable({ title, columns, rows, total }: { title: string; columns: string[]; rows: unknown[][]; total: number }) {
  const shown = rows.slice(0, 100)
  return (
    <figure className="glass overflow-hidden rounded-[var(--radius-card)]">
      <figcaption className="flex items-baseline justify-between gap-4 border-b hairline px-5 py-3">
        <span className="font-display text-lg">{title}</span>
        <span className="text-xs text-fg-3">{texts.run.rows(shown.length, total)}</span>
      </figcaption>
      <div className="max-h-[28rem] overflow-auto" data-lenis-prevent tabIndex={0} aria-label={title}>
        <table className="w-full border-collapse text-sm">
          <thead className="sticky top-0 z-10 bg-card-2">
            <tr>
              {columns.map((c) => (
                <th key={c} scope="col" className="whitespace-nowrap border-b hairline px-4 py-2.5 text-left font-semibold text-sun-300">{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((row, i) => (
              <tr key={i} className="odd:bg-fg/[0.02] hover:bg-magic-500/10">
                {row.map((v, j) => (
                  <td key={j} className={`whitespace-nowrap border-b hairline px-4 py-2 ${typeof v === 'number' ? 'text-right tabular-nums' : 'text-fg-2'}`}>{cell(v)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  )
}
