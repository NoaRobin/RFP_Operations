/**
 * Clavier 3D de la Recherche QviAPI (React Three Fiber) : il monte de sous la page à l'arrivée (GSAP), chaque touche
 * tapée s'enfonce et s'allume, et une onde parcourt le clavier pendant que les moteurs cherchent.
 * Décoratif (aria-hidden) ; jamais affiché en mouvement réduit ni sans WebGL (la recherche marche sans).
 */
import { useEffect, useMemo, useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { gsap } from '../../motion/gsap'

const ROWS = ['AZERTYUIOP', 'QSDFGHJKLM', 'WXCVBN?!']
const KEY = 0.92
const GAP = 0.14

function capTexture(letter: string): THREE.CanvasTexture {
  const c = document.createElement('canvas')
  c.width = c.height = 128
  const g = c.getContext('2d')!
  g.fillStyle = '#f6f8fa'
  g.fillRect(0, 0, 128, 128)
  g.strokeStyle = 'rgba(175,184,193,0.9)'
  g.lineWidth = 3
  g.strokeRect(6, 6, 116, 116)
  g.fillStyle = '#59636e'
  g.font = '600 56px -apple-system, "Segoe UI", system-ui, sans-serif'
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  g.fillText(letter, 64, 70)
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  t.anisotropy = 4
  return t
}

interface Cap { letter: string; x: number; z: number; w: number }

function layout(): Cap[] {
  const caps: Cap[] = []
  ROWS.forEach((row, r) => {
    const width = row.length * (KEY + GAP)
    row.split('').forEach((letter, i) => caps.push({ letter, x: i * (KEY + GAP) - width / 2 + KEY / 2 + r * 0.32, z: r * (KEY + GAP), w: KEY }))
  })
  caps.push({ letter: ' ', x: 0.3, z: 3 * (KEY + GAP), w: KEY * 6 })
  return caps
}

function Keys({ pressed, busy }: { pressed: React.MutableRefObject<string>; busy: boolean }) {
  const caps = useMemo(layout, [])
  const meshes = useRef<(THREE.Mesh | null)[]>([])
  const glow = useRef<number[]>(caps.map(() => 0))
  const geometries = useMemo(() => caps.map((c) => new THREE.BoxGeometry(c.w, 0.42, KEY)), [caps])
  const materials = useMemo(() => caps.map((c) => {
    const top = new THREE.MeshStandardMaterial({ map: c.letter.trim() ? capTexture(c.letter) : null, color: c.letter.trim() ? '#ffffff' : '#f6f8fa',
      emissive: new THREE.Color('#0969da'), emissiveIntensity: 0, metalness: 0.1, roughness: 0.8 })
    const side = new THREE.MeshStandardMaterial({ color: '#d1d9e0', metalness: 0.1, roughness: 0.85 })
    return [side, side, top, side, side, side]
  }), [caps])
  useEffect(() => () => {
    geometries.forEach((g) => g.dispose())
    materials.forEach((m) => { (m[2] as THREE.MeshStandardMaterial).map?.dispose(); m[2].dispose(); m[0].dispose() })
  }, [geometries, materials])
  useFrame((state) => {
    const letter = pressed.current
    if (letter) {
      const i = caps.findIndex((c) => c.letter === letter)
      if (i >= 0) glow.current[i] = 1
      pressed.current = ''
    }
    const t = state.clock.elapsedTime
    caps.forEach((c, i) => {
      const m = meshes.current[i]
      if (!m) return
      const wave = busy ? Math.max(0, Math.sin(t * 6 - c.x * 0.9 - c.z * 0.6)) * 0.35 : 0
      glow.current[i] = Math.max(0, glow.current[i] - 0.035)
      const g = Math.max(glow.current[i], wave)
      ;(materials[i][2] as THREE.MeshStandardMaterial).emissiveIntensity = g * 0.9
      m.position.y = -g * 0.1
    })
  })
  return (
    <group>
      {caps.map((c, i) => (
        <mesh key={`${c.letter}-${i}`} ref={(el) => { meshes.current[i] = el }} geometry={geometries[i]} material={materials[i]} position={[c.x, 0, c.z]} />
      ))}
    </group>
  )
}

function Rig({ children }: { children: React.ReactNode }) {
  const group = useRef<THREE.Group>(null)
  useEffect(() => {
    if (!group.current) return
    group.current.position.set(0, -5, 2)
    const tl = gsap.timeline()
    tl.fromTo(group.current.position, { y: -5, z: 2 }, { y: 0, z: 0, duration: 0.6, ease: 'power3.out' })
    tl.fromTo(group.current.rotation, { x: 0.25 }, { x: -0.05, duration: 0.6, ease: 'power3.out' }, 0)
    return () => { tl.kill() }
  }, [])
  useFrame((state) => {
    if (!group.current) return
    group.current.rotation.y = THREE.MathUtils.lerp(group.current.rotation.y, state.pointer.x * 0.06, 0.05)
  })
  return <group ref={group}>{children}</group>  // pas de position en prop : React la réappliquerait à chaque rendu
}

export default function KeyboardScene({ pressed, busy }: { pressed: React.MutableRefObject<string>; busy: boolean }) {
  return (
    <div className="pointer-events-none h-36 w-full" aria-hidden="true">
      <Canvas dpr={[1, 1.6]} camera={{ position: [0, 6.2, 6.4], fov: 38 }} gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}
        onCreated={({ camera }) => camera.lookAt(0, 0, 1.6)}>
        <ambientLight intensity={0.9} />
        <directionalLight position={[2, 8, 6]} intensity={1.1} color="#ffffff" />
        <Rig>
          <Keys pressed={pressed} busy={busy} />
        </Rig>
      </Canvas>
    </div>
  )
}
