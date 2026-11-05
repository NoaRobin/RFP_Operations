/**
 * Mascottes des univers, dessinées à l'encre épaisse comme le reste de l'app (Mathilde, le livre qui court) :
 * Merlin le sorcier, Gus le mécano du Pit Stop, Alfred le majordome du Suivi. Décoratives : aria-hidden.
 */
import type { UniverseId } from './universes'

const INK = 'var(--color-fg)'

export function Wizard({ className = 'size-12' }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 120" className={className} aria-hidden="true" fill="none" stroke={INK} strokeWidth="4" strokeLinejoin="round" strokeLinecap="round">
      {/* chapeau étoilé, pointe qui retombe */}
      <path d="M22 56 C40 50 80 50 98 56 L92 62 C72 58 48 58 28 62 Z" fill="#7c5cff" />
      <path d="M32 56 C38 34 52 12 74 8 C68 18 70 28 78 34 C82 42 84 50 86 54" fill="#9b82ff" />
      <path d="M50 30 l3 6 6 1 -5 4 1 6 -5 -3 -5 3 1 -6 -5 -4 6 -1 z" fill="#ffd23f" strokeWidth="2.5" />
      <circle cx="70" cy="44" r="2.5" fill="#ffd23f" strokeWidth="2" />
      {/* visage */}
      <path d="M36 62 C36 80 84 80 84 62" fill="#ffe1c7" />
      <circle cx="50" cy="68" r="3" fill={INK} stroke="none" />
      <circle cx="70" cy="68" r="3" fill={INK} stroke="none" />
      <path d="M44 62 q6 -4 12 0 M64 62 q6 -4 12 0" strokeWidth="3" />
      {/* barbe en nuage */}
      <path d="M34 72 C30 92 44 112 60 114 C76 112 90 92 86 72 C80 82 70 84 60 82 C50 84 40 82 34 72 Z" fill="#ffffff" />
      <path d="M52 86 q8 6 16 0" strokeWidth="3" />
    </svg>
  )
}

export function Mechanic({ className = 'size-12' }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 120" className={className} aria-hidden="true" fill="none" stroke={INK} strokeWidth="4" strokeLinejoin="round" strokeLinecap="round">
      {/* casquette de stand, visière vers l'avant, éclair */}
      <path d="M28 50 C28 26 92 26 92 50 Z" fill="#2f6bff" />
      <path d="M86 50 C98 50 108 54 110 58 L86 58 Z" fill="#1a3fa8" />
      <path d="M58 32 l-6 10 h7 l-4 9 11 -13 h-7 l4 -6 z" fill="#14b8d4" strokeWidth="2.5" />
      {/* visage */}
      <path d="M30 50 C28 82 92 82 90 50 Z" fill="#ffd9b8" />
      <circle cx="48" cy="62" r="3.2" fill={INK} stroke="none" />
      <circle cx="72" cy="62" r="3.2" fill={INK} stroke="none" />
      <path d="M46 74 q14 10 28 0" strokeWidth="3.5" />
      <path d="M78 68 q6 2 8 -2" strokeWidth="2.5" />{/* trace de cambouis */}
      {/* casque audio + micro (le stand parle au pilote) */}
      <path d="M26 56 C20 40 30 24 44 20" strokeWidth="3.5" />
      <rect x="20" y="52" width="10" height="16" rx="4" fill="#14b8d4" />
      <path d="M26 68 C30 80 40 84 46 82" strokeWidth="3" />
      <circle cx="47" cy="82" r="3" fill={INK} stroke="none" />
      {/* combinaison + clé à molette */}
      <path d="M34 86 C40 80 80 80 86 86 L92 114 H28 Z" fill="#2f6bff" />
      <path d="M60 84 V114" strokeWidth="3" />
      <rect x="44" y="94" width="10" height="8" rx="1.5" fill="#ffffff" strokeWidth="2.5" />
      <path d="M96 78 l14 -14 M104 60 a7 7 0 1 1 10 10 l-4 -2 -4 -4 z" fill="#c8dbff" strokeWidth="3.5" />
    </svg>
  )
}

export function Butler({ className = 'size-12' }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 120" className={className} aria-hidden="true" fill="none" stroke={INK} strokeWidth="4" strokeLinejoin="round" strokeLinecap="round">
      {/* cheveux plaqués, raie impeccable */}
      <path d="M34 48 C34 22 86 22 86 48 C78 40 66 36 56 40 C48 36 40 40 34 48 Z" fill="#3a3352" />
      <path d="M34 48 C32 78 88 78 86 48" fill="#ffe1c7" />
      {/* sourcils levés, monocle */}
      <path d="M44 54 q6 -5 12 0" strokeWidth="3" />
      <path d="M64 52 q6 -5 12 0" strokeWidth="3" />
      <circle cx="50" cy="60" r="2.8" fill={INK} stroke="none" />
      <circle cx="70" cy="60" r="7" fill="#ffffff" strokeWidth="3" />
      <circle cx="70" cy="60" r="2.8" fill={INK} stroke="none" />
      <path d="M76 64 q4 10 0 22" strokeWidth="2" />
      {/* moustache */}
      <path d="M48 70 C54 66 58 68 60 70 C62 68 66 66 72 70 C66 74 62 72 60 72 C58 72 54 74 48 70 Z" fill="#3a3352" strokeWidth="2.5" />
      {/* habit, plastron, nœud papillon */}
      <path d="M30 86 C38 78 82 78 90 86 L96 116 H24 Z" fill="#1b1530" />
      <path d="M50 80 L60 108 L70 80 Z" fill="#ffffff" strokeWidth="3" />
      <path d="M50 84 L60 89 L70 84 L70 94 L60 89 L50 94 Z" fill="#2ec4b6" strokeWidth="2.5" />
      {/* plateau avec le registre */}
      <path d="M90 92 H116" strokeWidth="4" />
      <rect x="96" y="80" width="16" height="12" rx="2" fill="#fff6e5" strokeWidth="3" />
    </svg>
  )
}

export function Mascot({ universe, className }: { universe: UniverseId; className?: string }) {
  if (universe === 'pitstop') return <Mechanic className={className} />
  if (universe === 'suivi') return <Butler className={className} />
  return <Wizard className={className} />
}
