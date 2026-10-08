export type Mood = 'calm' | 'awaken' | 'focus' | 'success' | 'failure'

/** Humeurs du grimoire vivant (partagées entre la 3D et le repli 2D). */
export const MOODS: Record<Mood, {
  speed: number
  packets: number
  scale: number
  fall: number
  linkOpacity: number
  ringOpacity: number
  node: string
  core: string
  label: string
}> = {
  calm: { speed: 0.08, packets: 0.25, scale: 1, fall: 0, linkOpacity: 0.22, ringOpacity: 0.28, node: '#b7c6da', core: '#8fa6c3', label: 'au repos' },
  awaken: { speed: 0.16, packets: 0.5, scale: 1.04, fall: 0, linkOpacity: 0.32, ringOpacity: 0.45, node: '#efe2c4', core: '#e3cfa1', label: 'en éveil' },
  focus: { speed: 0.42, packets: 1.6, scale: 0.9, fall: 0, linkOpacity: 0.42, ringOpacity: 0.55, node: '#b5d6cb', core: '#86bfae', label: 'en calcul' },
  success: { speed: 0.12, packets: 0.6, scale: 1.06, fall: 0, linkOpacity: 0.34, ringOpacity: 0.6, node: '#e3cfa1', core: '#efe2c4', label: 'terminé' },
  failure: { speed: 0.02, packets: 0, scale: 0.98, fall: 1, linkOpacity: 0.07, ringOpacity: 0.1, node: '#5d6472', core: '#3a404b', label: 'en échec' },
}
