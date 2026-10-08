/**
 * « Le livre vivant » : la signature 3D de RFP pas envie de travailler, chargée à la demande.
 * Un livre de sorts cartoon (ombrage toon 3 tons + contour d'encre par coque inversée) qui a des yeux,
 * suit le curseur, s'ouvre quand il travaille, feuillette ses pages, et fait jaillir des étoiles quand c'est réussi.
 * Budget : une vingtaine de meshes simples, aucune texture externe, DPR plafonné à 1,5, repli 2D si les FPS chutent.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { PerformanceMonitor } from '@react-three/drei'
import * as THREE from 'three'
import { MOODS, type Mood } from './moods'

const damp = THREE.MathUtils.damp
const INK = '#1b1530'
const W = 2.2
const H = 2.8
const COVER = 0.14
const PAGES = 0.36

interface SceneProps { mood: Mood; reduced: boolean; onPoke?: () => void; burstKey: number }

/** Dégradé 3 tons, filtrage « nearest » : c'est ce qui donne l'aplat cartoon. */
function useToonGradient() {
  return useMemo(() => {
    const data = new Uint8Array([90, 90, 90, 255, 180, 180, 180, 255, 255, 255, 255, 255])
    const texture = new THREE.DataTexture(data, 3, 1, THREE.RGBAFormat)
    texture.minFilter = THREE.NearestFilter
    texture.magFilter = THREE.NearestFilter
    texture.generateMipmaps = false
    texture.needsUpdate = true
    return texture
  }, [])
}

const outlineMaterial = new THREE.MeshBasicMaterial({ color: INK, side: THREE.BackSide })
const inkFill = new THREE.MeshBasicMaterial({ color: INK })

/** Boîte toon + contour d'encre (coque inversée légèrement plus grande). */
function InkBox({ size, color, gradient, position, materialRef }: {
  size: [number, number, number]; color: string; gradient: THREE.Texture; position?: [number, number, number]
  materialRef?: (m: THREE.MeshToonMaterial | null) => void
}) {
  const t = 0.045
  return (
    <group position={position}>
      <mesh>
        <boxGeometry args={size} />
        <meshToonMaterial ref={materialRef} color={color} gradientMap={gradient} />
      </mesh>
      <mesh material={outlineMaterial}>
        <boxGeometry args={[size[0] + t * 2, size[1] + t * 2, size[2] + t * 2]} />
      </mesh>
    </group>
  )
}

function starShape(outer = 0.32, inner = 0.14) {
  const shape = new THREE.Shape()
  for (let i = 0; i < 10; i++) {
    const r = i % 2 === 0 ? outer : inner
    const a = (i / 10) * Math.PI * 2 + Math.PI / 2
    const x = Math.cos(a) * r
    const y = Math.sin(a) * r
    if (i === 0) shape.moveTo(x, y)
    else shape.lineTo(x, y)
  }
  shape.closePath()
  return shape
}

/** Un œil cartoon : blanc, pupille qui suit le curseur, paupière qui cligne. */
function Eye({ x, pupils, lids }: { x: number; pupils: React.MutableRefObject<THREE.Mesh[]>; lids: React.MutableRefObject<THREE.Mesh[]> }) {
  return (
    <group position={[x, 0.35, COVER / 2 + 0.01]}>
      <mesh scale={[1, 1.25, 1]}>
        <circleGeometry args={[0.26, 40]} />
        <meshBasicMaterial color="#ffffff" />
      </mesh>
      <mesh scale={[1, 1.25, 1]} position={[0, 0, -0.004]}>
        <circleGeometry args={[0.31, 40]} />
        <meshBasicMaterial color={INK} />
      </mesh>
      <mesh ref={(m) => { if (m && !pupils.current.includes(m)) pupils.current.push(m) }} position={[0, 0, 0.006]}>
        <circleGeometry args={[0.12, 32]} />
        <meshBasicMaterial color={INK} />
      </mesh>
      {/* Paupière : un aplat violet qui descend depuis le haut */}
      <mesh ref={(m) => { if (m && !lids.current.includes(m)) lids.current.push(m) }} position={[0, 0.33, 0.012]} scale={[1, 0.001, 1]}>
        <planeGeometry args={[0.66, 0.66]} />
        <meshBasicMaterial color="#6a4bea" />
      </mesh>
    </group>
  )
}

function LivingBook({ mood, reduced, onPoke, burstKey }: SceneProps) {
  const gradient = useToonGradient()
  const m = MOODS[mood]
  const root = useRef<THREE.Group>(null)
  const body = useRef<THREE.Group>(null)
  const cover = useRef<THREE.Group>(null)
  const flip = useRef<THREE.Group>(null)
  const orbit = useRef<THREE.Group>(null)
  const stars = useRef<THREE.Group[]>([])
  const sheets = useRef<THREE.Group[]>([])
  const pupils = useRef<THREE.Mesh[]>([])
  const lids = useRef<THREE.Mesh[]>([])
  const coverMaterials = useRef<THREE.MeshToonMaterial[]>([])
  const pointer = useThree((s) => s.pointer)
  const live = useRef({ open: 0.4, speed: 0.1, squash: 0, burst: -10, blink: 2, gray: 0 })
  const starGeometry = useMemo(() => new THREE.ExtrudeGeometry(starShape(), { depth: 0.12, bevelEnabled: true, bevelSize: 0.03, bevelThickness: 0.03, bevelSegments: 1 }).center(), [])
  const starOutline = useMemo(() => new THREE.ExtrudeGeometry(starShape(0.4, 0.19), { depth: 0.04, bevelEnabled: false }), [])
  const purple = useMemo(() => ({ base: new THREE.Color('#7c5cff'), sad: new THREE.Color('#8a86a0'), tmp: new THREE.Color() }), [])

  const STARS = 6
  const SHEETS = 7

  useEffect(() => {
    if (burstKey) live.current.burst = 0
  }, [burstKey])

  useFrame((state, delta) => {
    const dt = Math.min(delta, 0.05)
    const t = state.clock.elapsedTime
    const L = live.current
    const target = {
      open: mood === 'focus' ? 2.35 : mood === 'success' ? 1.9 : mood === 'failure' ? 0.02 : mood === 'awaken' ? 0.9 : 0.45,
      speed: m.speed,
      gray: mood === 'failure' ? 1 : 0,
    }
    L.open = damp(L.open, target.open, 4, dt)
    L.speed = damp(L.speed, target.speed, 3, dt)
    L.gray = damp(L.gray, target.gray, 3, dt)
    L.squash = damp(L.squash, 0, 7, dt)
    if (L.burst >= 0) L.burst += dt

    if (root.current) {
      const bob = reduced ? 0 : Math.sin(t * 1.6) * 0.12
      root.current.position.y = bob - (mood === 'failure' ? 0.35 : 0)
      root.current.rotation.y = damp(root.current.rotation.y, 0.45 + pointer.x * 0.35, 3, dt)
      root.current.rotation.x = damp(root.current.rotation.x, 0.12 - pointer.y * 0.2 + (mood === 'failure' ? 0.25 : 0), 3, dt)
      root.current.rotation.z = reduced ? 0 : Math.sin(t * 1.1) * 0.04 + (mood === 'failure' ? -0.18 : 0)
    }
    if (body.current) {
      const s = L.squash
      body.current.scale.set(1 + s * 0.12, 1 - s * 0.15, 1 + s * 0.12)
    }
    if (cover.current) cover.current.rotation.y = -L.open
    // Page qui se tourne en boucle quand le livre travaille
    if (flip.current) {
      const flipping = mood === 'focus' && !reduced
      flip.current.visible = flipping
      if (flipping) flip.current.rotation.y = -((t * 1.8) % 1) * Math.min(L.open, 2.3)
    }
    // Yeux : suivent le curseur, clignent de temps en temps, mi-clos en cas d'échec
    L.blink -= dt
    const blinking = !reduced && L.blink < 0.12
    if (L.blink < 0) L.blink = 2.5 + Math.random() * 3
    const lid = mood === 'failure' ? 0.55 : blinking ? 1 : mood === 'focus' ? 0.25 : 0
    pupils.current.forEach((p) => {
      p.position.x = damp(p.position.x, THREE.MathUtils.clamp(pointer.x * 0.12, -0.12, 0.12), 8, dt)
      p.position.y = damp(p.position.y, mood === 'failure' ? -0.12 : THREE.MathUtils.clamp(pointer.y * 0.14, -0.14, 0.16), 8, dt)
    })
    lids.current.forEach((l) => {
      const k = damp(l.scale.y, Math.max(lid, 0.001), blinking ? 30 : 10, dt)
      l.scale.y = k
      l.position.y = 0.33 - (k * 0.66) / 2 + 0.0
    })
    // Couleur de couverture : se ternit en cas d'échec
    purple.tmp.copy(purple.base).lerp(purple.sad, L.gray)
    coverMaterials.current.forEach((mat) => mat.color.copy(purple.tmp))

    // Étoiles en orbite (+ jaillissement au succès)
    const burst = L.burst >= 0 && L.burst < 1.6 ? Math.sin((L.burst / 1.6) * Math.PI) : 0
    stars.current.forEach((g, i) => {
      if (!g) return
      const a = (i / STARS) * Math.PI * 2 + t * L.speed * 2.2
      const r = 2.25 + burst * 1.6 + (mood === 'focus' ? -0.35 : 0)
      g.position.set(Math.cos(a) * r, Math.sin(a * 1.3 + i) * 0.6 + (i % 2 ? 0.5 : -0.4) - L.gray * 1.2, Math.sin(a) * r * 0.55)
      g.rotation.z = reduced ? 0 : t * (1 + i * 0.2)
      g.rotation.y = reduced ? 0 : t * 0.8
      const pop = 1 + burst * 0.8
      const sc = (mood === 'failure' ? 0.6 : 1) * pop
      g.scale.setScalar(damp(g.scale.x, sc, 6, dt))
    })
    // Feuilles de questionnaire aspirées vers le livre quand il travaille
    sheets.current.forEach((g, i) => {
      if (!g) return
      const show = mood === 'focus' || mood === 'success' ? 1 : mood === 'awaken' ? 0.6 : 0
      const a = (i / SHEETS) * Math.PI * 2 - t * (0.4 + L.speed * 3)
      const r = mood === 'focus' ? 1.7 + Math.sin(t * 2 + i) * 0.35 : 2.9
      g.position.set(Math.cos(a) * r, Math.sin(t * 1.5 + i * 1.7) * 1.1, Math.sin(a) * r * 0.6)
      g.rotation.set(Math.sin(t + i) * 0.5, a + Math.PI / 2, Math.cos(t * 1.3 + i) * 0.4)
      g.scale.setScalar(damp(g.scale.x, show * (0.9 + (i % 3) * 0.12), 4, dt) || 0.0001)
    })
    if (orbit.current) orbit.current.rotation.x = 0.15
  })

  const poke = (e: { stopPropagation: () => void }) => {
    e.stopPropagation()
    live.current.squash = 1
    live.current.burst = 0
    onPoke?.()
  }

  return (
    <group ref={root}>
      <group ref={body} onClick={onPoke ? poke : undefined} onPointerOver={() => onPoke && (document.body.style.cursor = 'pointer')} onPointerOut={() => (document.body.style.cursor = '')}>
        {/* Couverture arrière */}
        <InkBox size={[W, H, COVER]} color="#7c5cff" gradient={gradient} position={[0, 0, -PAGES / 2 - COVER / 2]}
          materialRef={(mat) => { if (mat && !coverMaterials.current.includes(mat)) coverMaterials.current.push(mat) }} />
        {/* Bloc de pages */}
        <InkBox size={[W - 0.16, H - 0.18, PAGES]} color="#fffaf0" gradient={gradient} position={[0.04, 0, 0]} />
        {[-0.08, 0, 0.08].map((z) => (
          <mesh key={z} position={[W / 2 - 0.035, 0, z]}>
            <boxGeometry args={[0.012, H - 0.3, 0.01]} />
            <meshBasicMaterial color="#d9cfb8" />
          </mesh>
        ))}
        {/* Dos */}
        <InkBox size={[COVER, H, PAGES + COVER * 2]} color="#6a4bea" gradient={gradient} position={[-W / 2 - COVER / 2 + 0.02, 0, 0]} />
        {/* Page qui se tourne */}
        <group ref={flip} position={[-W / 2 + 0.06, 0, PAGES / 2 + 0.01]} visible={false}>
          <mesh position={[(W - 0.2) / 2, 0, 0]}>
            <planeGeometry args={[W - 0.2, H - 0.25]} />
            <meshToonMaterial color="#ffffff" gradientMap={gradient} side={THREE.DoubleSide} />
          </mesh>
        </group>
        {/* Couverture avant, articulée sur le dos */}
        <group ref={cover} position={[-W / 2, 0, PAGES / 2 + COVER / 2]}>
          <group position={[W / 2, 0, 0]}>
            <InkBox size={[W, H, COVER]} color="#7c5cff" gradient={gradient}
              materialRef={(mat) => { if (mat && !coverMaterials.current.includes(mat)) coverMaterials.current.push(mat) }} />
            <Eye x={-0.42} pupils={pupils} lids={lids} />
            <Eye x={0.42} pupils={pupils} lids={lids} />
            {/* Étoile dorée sur la couverture */}
            <group position={[0, -0.62, COVER / 2 + 0.04]} scale={0.95}>
              <mesh geometry={starGeometry}>
                <meshToonMaterial color="#ffd23f" gradientMap={gradient} />
              </mesh>
              <mesh geometry={starOutline} position={[0, 0, -0.035]} material={inkFill} />
            </group>
            {/* Coins dorés */}
            {[[-1, 1], [1, 1], [-1, -1], [1, -1]].map(([sx, sy]) => (
              <mesh key={`${sx}${sy}`} position={[sx * (W / 2 - 0.16), sy * (H / 2 - 0.16), COVER / 2 + 0.006]}>
                <circleGeometry args={[0.09, 20]} />
                <meshBasicMaterial color="#ffd23f" />
              </mesh>
            ))}
          </group>
        </group>
      </group>

      <group ref={orbit}>
        {Array.from({ length: STARS }, (_, i) => (
          <group key={`s${i}`} ref={(g) => { if (g) stars.current[i] = g }} scale={0.0001}>
            <mesh geometry={starGeometry}>
              <meshToonMaterial color={i % 3 === 0 ? '#ff6b9a' : i % 3 === 1 ? '#ffd23f' : '#2ec4b6'} gradientMap={gradient} />
            </mesh>
            <mesh geometry={starGeometry} scale={[1.2, 1.2, 1.6]} material={outlineMaterial} />
          </group>
        ))}
        {Array.from({ length: SHEETS }, (_, i) => (
          <group key={`p${i}`} ref={(g) => { if (g) sheets.current[i] = g }} scale={0.0001}>
            <mesh>
              <planeGeometry args={[0.42, 0.56]} />
              <meshBasicMaterial color="#ffffff" side={THREE.DoubleSide} />
            </mesh>
            <mesh position={[0, 0, -0.008]}>
              <planeGeometry args={[0.5, 0.64]} />
              <meshBasicMaterial color={INK} side={THREE.DoubleSide} />
            </mesh>
            {[0.15, 0.05, -0.05, -0.15].map((y, k) => (
              <mesh key={y} position={[-0.03 + (k % 2) * 0.02, y, 0.004]}>
                <planeGeometry args={[k % 2 ? 0.22 : 0.28, 0.035]} />
                <meshBasicMaterial color={k === 0 ? '#7c5cff' : '#c9c2dc'} side={THREE.DoubleSide} />
              </mesh>
            ))}
          </group>
        ))}
      </group>
    </group>
  )
}

/** Recule la caméra dans les cadres étroits pour que le livre ne soit jamais rogné. */
function CameraFit() {
  const { camera, size } = useThree()
  useEffect(() => {
    const aspect = size.width / Math.max(size.height, 1)
    camera.position.z = aspect >= 1 ? 8.2 : 8.2 / Math.pow(aspect, 0.85)
    camera.updateProjectionMatrix()
  }, [camera, size])
  return null
}

export default function BookScene({ mood, reduced, onPoke, burstKey, onDegrade }: SceneProps & { onDegrade?: () => void }) {
  const container = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(true)
  const [dpr, setDpr] = useState(1.5)

  useEffect(() => {
    const el = container.current
    if (!el) return
    const io = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting && !document.hidden))
    io.observe(el)
    const onVis = () => setVisible(!document.hidden)
    document.addEventListener('visibilitychange', onVis)
    return () => {
      io.disconnect()
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [])

  return (
    <div ref={container} className="absolute inset-0" aria-hidden="true">
      <Canvas
        dpr={[1, dpr]}
        resize={{ offsetSize: true }}
        frameloop={visible ? 'always' : 'never'}
        camera={{ position: [0, 0, 8.2], fov: 40 }}
        gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}
        onCreated={({ gl }) => gl.setClearColor(0x000000, 0)}
      >
        <PerformanceMonitor onDecline={() => setDpr(1)} flipflops={3} onFallback={() => onDegrade?.()} />
        <CameraFit />
        <ambientLight intensity={1.4} />
        <directionalLight position={[3, 4, 5]} intensity={2.2} />
        <LivingBook mood={mood} reduced={reduced} onPoke={onPoke} burstKey={burstKey} />
      </Canvas>
    </div>
  )
}
