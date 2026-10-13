/** État de revue d'une question, tel que l'utilisateur le perçoit (indépendant du statut moteur). */
import type { RfiQuestion } from '../../../lib/types'

export type Override = string | null | { text: string; source?: 'copilot'; citation?: string; confidence?: string; previous?: string | null }
export type ReviewState = 'auto' | 'accepted' | 'review' | 'none' | 'skipped' | 'existing'

export function reviewState(q: RfiQuestion, accepted: Set<string>, override: Override | undefined): ReviewState {
  if (override === null || q.status === 'skipped') return 'skipped'
  // Copilot : toujours à vérifier tant qu'un humain n'a pas validé
  if (override && typeof override === 'object' && override.source === 'copilot') return accepted.has(q.id) ? 'accepted' : 'review'
  if (override !== undefined && typeof override === 'object') return override.text.trim() ? 'accepted' : 'none'
  if (q.status === 'existing') return 'existing'
  if (q.status === 'auto') return 'auto'
  if (q.status === 'review' && q.answer != null) return accepted.has(q.id) ? 'accepted' : 'review'
  return 'none'
}

export const STATE_STYLE: Record<ReviewState, string> = {
  auto: 'bg-mint-400',
  accepted: 'bg-magic-400 text-white',
  review: 'bg-sun-400',
  none: 'bg-[#ffd6dc]',
  skipped: 'bg-card-2 text-fg-3',
  existing: 'bg-card-3',
}

export const STATE_DOT: Record<ReviewState, string> = {
  auto: 'bg-mint-400', accepted: 'bg-magic-400', review: 'bg-sun-400', none: 'bg-bubble-400', skipped: 'bg-card-3', existing: 'bg-card-3',
}
