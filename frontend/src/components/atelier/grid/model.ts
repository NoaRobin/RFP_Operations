/**
 * Lecture « matrice » d'une analyse du compléteur RFI : ISIN sur le côté, questions en haut.
 * Les cases des grilles par part (une ligne ou une colonne par ISIN dans le fichier) sont regroupées par feuille ;
 * l'orientation du fichier ne change rien à l'affichage (toujours ISIN en lignes), le fichier rendu garde la sienne.
 */
import type { DocumentShare, RfiAnalysis, RfiQuestion } from '../../../lib/types'
import { reviewState, type Override, type ReviewState } from '../../rfi/review/state'

export interface GridColumn {
  key: string
  question: string
  ids: string[]
  concept: string | null
  conceptLabel: string | null
}
export interface GridRow { isin: string; share: DocumentShare | null; cells: Record<string, RfiQuestion> }
export interface Grid { sheet: string; orientation: 'rows' | 'columns'; columns: GridColumn[]; rows: GridRow[] }

const sheetOf = (q: RfiQuestion) => q.location.split('!')[0]

export function buildGrids(analysis: RfiAnalysis, shares: DocumentShare[]): { grids: Grid[]; others: RfiQuestion[] } {
  const byIsin = new Map(shares.map((s) => [s.isin, s]))
  const grids = new Map<string, Grid>()
  const others: RfiQuestion[] = []
  for (const q of analysis.questions) {
    const isin = q.entity?.isin
    if (!isin || (q.layout !== 'row-grid' && q.layout !== 'column-grid')) { others.push(q); continue }
    const sheet = sheetOf(q)
    let g = grids.get(sheet)
    if (!g) {
      g = { sheet, orientation: q.layout === 'column-grid' ? 'columns' : 'rows', columns: [], rows: [] }
      grids.set(sheet, g)
    }
    let col = g.columns.find((c) => c.question === q.question)
    if (!col) {
      col = { key: `${sheet}|${q.question}`, question: q.question, ids: [], concept: null, conceptLabel: null }
      g.columns.push(col)
    }
    col.ids.push(q.id)
    let row = g.rows.find((r) => r.isin === isin)
    if (!row) {
      row = { isin, share: byIsin.get(isin) ?? null, cells: {} }
      g.rows.push(row)
    }
    row.cells[col.key] = q
  }
  for (const g of grids.values()) {
    for (const col of g.columns) {  // donnée la plus fréquente de la colonne
      const counts = new Map<string, { n: number; label: string | null }>()
      for (const r of g.rows) {
        const q = r.cells[col.key]
        if (q?.concept) counts.set(q.concept, { n: (counts.get(q.concept)?.n ?? 0) + 1, label: q.concept_label })
      }
      const best = [...counts.entries()].sort((a, b) => b[1].n - a[1].n)[0]
      if (best) { col.concept = best[0]; col.conceptLabel = best[1].label }
    }
  }
  return { grids: [...grids.values()], others }
}

export type States = Record<string, ReviewState>

export function statesOf(analysis: RfiAnalysis, accepted: Set<string>, overrides: Record<string, Override>): States {
  return Object.fromEntries(analysis.questions.map((q) => [q.id, reviewState(q, accepted, overrides[q.id])]))
}

/** Part des cases qui seront écrites (sûres, acceptées, choisies) parmi celles d'une liste. */
export function filled(ids: string[], states: States): number {
  if (!ids.length) return 0
  return ids.filter((id) => states[id] === 'auto' || states[id] === 'accepted').length / ids.length
}
