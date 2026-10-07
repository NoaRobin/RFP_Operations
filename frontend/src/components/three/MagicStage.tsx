/** Choisit 3D ou 2D automatiquement, charge la 3D en différé et retombe en 2D si quoi que ce soit échoue. */
import { Component, lazy, Suspense, useEffect, useRef, useState, type ReactNode } from 'react'
import { canUse3D } from '../../lib/perf'
import { useLowPowerPref } from '../../lib/storage'
import { useReducedMotion } from '../../motion/useReducedMotion'
import OrbFallback from './OrbFallback'
import type { Mood } from './moods'

const OrbScene = lazy(() => import('./OrbScene'))

class SceneBoundary extends Component<{ fallback: ReactNode; children: ReactNode; onError: () => void }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  componentDidCatch() {
    this.props.onError()
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

export function MagicStage({ mood, onPoke, className = '' }: { mood: Mood; onPoke?: () => void; className?: string }) {
  const reduced = useReducedMotion()
  const lowPower = useLowPowerPref()
  const [degraded, setDegraded] = useState(false)
  const [burstKey, setBurstKey] = useState(0)
  const previous = useRef<Mood>(mood)
  const use3D = !degraded && !lowPower && canUse3D()

  // Explosion d'étincelles à l'entrée en succès (et petit feu d'artifice au clic).
  useEffect(() => {
    if (mood === 'success' && previous.current !== 'success') setBurstKey((k) => k + 1)
    previous.current = mood
  }, [mood])

  const poke = onPoke
    ? () => {
        setBurstKey((k) => k + 1)
        onPoke()
      }
    : undefined

  const fallback = <OrbFallback mood={mood} reduced={reduced} onPoke={poke} burstKey={burstKey} />
  return (
    <div className={className || 'relative'}>
      {use3D ? (
        <SceneBoundary fallback={fallback} onError={() => setDegraded(true)}>
          <Suspense fallback={fallback}>
            <OrbScene mood={mood} reduced={reduced} onPoke={poke} burstKey={burstKey} onDegrade={() => setDegraded(true)} />
          </Suspense>
        </SceneBoundary>
      ) : (
        fallback
      )}
    </div>
  )
}
