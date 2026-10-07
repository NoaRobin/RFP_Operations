export type Mood = 'calm' | 'awaken' | 'focus' | 'success' | 'failure'

/** Paramètres de chaque humeur du cristal (partagés entre la 3D et le repli 2D). */
export const MOODS: Record<Mood, {
  speed: number
  spread: number
  rise: number
  glow: number
  droop: number
  colorA: string
  colorB: string
  emissive: string
  label: string
}> = {
  calm: { speed: 0.18, spread: 1, rise: 0, glow: 0.55, droop: 0, colorA: '#a78bfa', colorB: '#5eead4', emissive: '#3b1d8f', label: 'au repos' },
  awaken: { speed: 0.35, spread: 1.15, rise: 0, glow: 1, droop: 0, colorA: '#f5dfa5', colorB: '#a78bfa', emissive: '#6d28d9', label: 'qui s\'éveille' },
  focus: { speed: 1.1, spread: 0.72, rise: 0, glow: 1.25, droop: 0, colorA: '#5eead4', colorB: '#a78bfa', emissive: '#0e7490', label: 'concentré' },
  success: { speed: 0.5, spread: 1.3, rise: 0, glow: 1.6, droop: 0, colorA: '#f5dfa5', colorB: '#5eead4', emissive: '#b8913f', label: 'triomphant' },
  failure: { speed: 0.06, spread: 1.05, rise: 1, glow: 0.18, droop: 0.35, colorA: '#6b6585', colorB: '#3f3a55', emissive: '#1a1726', label: 'vexé' },
}
