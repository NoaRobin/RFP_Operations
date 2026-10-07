/**
 * « Constellation de données » : la signature 3D de MERIDIAN. Chargée à la demande.
 * Budget : nœuds en InstancedMesh (1 draw call), liens en LineSegments (1), paquets de données en Points (1),
 * méridiens (3 lignes), cœur (1). DPR plafonné à 1,5 ; baisse automatique si les FPS chutent.
 * Réagit à l'état : calme, calcul (contraction + flux), succès (onde champagne), échec (effondrement).
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { PerformanceMonitor } from '@react-three/drei'
import * as THREE from 'three'
import { MOODS, type Mood } from './moods'
import { particleBudget } from '../../lib/perf'

const damp = THREE.MathUtils.damp
const RADIUS = 1.85
const CHAMPAGNE = new THREE.Color('#e3cfa1')

interface SceneProps { mood: Mood; reduced: boolean; onPoke?: () => void; burstKey: number }

/** Points répartis régulièrement sur une sphère (spirale de Fibonacci). */
function fibonacciSphere(count: number, radius: number): THREE.Vector3[] {
  const points: THREE.Vector3[] = []
  const golden = Math.PI * (3 - Math.sqrt(5))
  for (let i = 0; i < count; i++) {
    const y = 1 - (i / (count - 1)) * 2
    const r = Math.sqrt(1 - y * y)
    const theta = golden * i
    const jitter = 1 + (Math.random() - 0.5) * 0.12
    points.push(new THREE.Vector3(Math.cos(theta) * r, y, Math.sin(theta) * r).multiplyScalar(radius * jitter))
  }
  return points
}

function useGraph() {
  return useMemo(() => {
    const count = Math.max(90, particleBudget(320))
    const nodes = fibonacciSphere(count, RADIUS)
    const links: [number, number][] = []
    const seen = new Set<string>()
    nodes.forEach((a, i) => {
      const nearest = nodes
        .map((b, j) => ({ j, d: a.distanceToSquared(b) }))
        .filter((x) => x.j !== i)
        .sort((x, y) => x.d - y.d)
        .slice(0, 2)
      for (const { j } of nearest) {
        const key = i < j ? `${i}-${j}` : `${j}-${i}`
        if (!seen.has(key)) {
          seen.add(key)
          links.push([i, j])
        }
      }
    })
    const adjacency: number[][] = nodes.map(() => [])
    links.forEach(([a, b], k) => {
      adjacency[a].push(k)
      adjacency[b].push(k)
    })
    const fall = nodes.map(() => 0.4 + Math.random() * 1.6)
    return { nodes, links, adjacency, fall }
  }, [])
}

function Constellation({ mood, reduced, onPoke, burstKey }: SceneProps) {
  const { nodes, links, adjacency, fall } = useGraph()
  const group = useRef<THREE.Group>(null)
  const instanced = useRef<THREE.InstancedMesh>(null)
  const linkMaterial = useRef<THREE.LineBasicMaterial>(null)
  const ringMaterials = useRef<THREE.LineBasicMaterial[]>([])
  const core = useRef<THREE.Mesh>(null)
  const packetsRef = useRef<THREE.Points>(null)
  const pointer = useThree((s) => s.pointer)
  const clock = useThree((s) => s.clock)
  const state = useRef({ speed: 0.08, packets: 0.25, scale: 1, fall: 0, links: 0.2, rings: 0.3, wave: -10, poke: 0 })
  const tmp = useMemo(() => ({ m: new THREE.Matrix4(), c: new THREE.Color(), cur: new THREE.Color(), base: new THREE.Color(), q: new THREE.Quaternion(), s: new THREE.Vector3(), p: new THREE.Vector3() }), [])

  // Géométrie des liens
  const linkGeometry = useMemo(() => {
    const positions = new Float32Array(links.length * 6)
    links.forEach(([a, b], k) => {
      positions.set([nodes[a].x, nodes[a].y, nodes[a].z, nodes[b].x, nodes[b].y, nodes[b].z], k * 6)
    })
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    return g
  }, [links, nodes])

  // Méridiens : trois grands cercles + un équateur
  const rings = useMemo(() => {
    const circle = (r: number) => {
      const pts: THREE.Vector3[] = []
      for (let i = 0; i <= 128; i++) {
        const a = (i / 128) * Math.PI * 2
        pts.push(new THREE.Vector3(Math.cos(a) * r, Math.sin(a) * r, 0))
      }
      return new THREE.BufferGeometry().setFromPoints(pts)
    }
    return [
      { geometry: circle(RADIUS * 1.22), rotation: [0, 0, 0] as const },
      { geometry: circle(RADIUS * 1.22), rotation: [0, Math.PI / 3, 0] as const },
      { geometry: circle(RADIUS * 1.22), rotation: [0, (2 * Math.PI) / 3, 0] as const },
      { geometry: circle(RADIUS * 1.32), rotation: [Math.PI / 2, 0, 0.18] as const },
    ]
  }, [])

  // Paquets de données qui circulent sur les liens
  const packetCount = reduced ? 0 : Math.round(particleBudget(48))
  const packets = useMemo(
    () => Array.from({ length: packetCount }, () => ({ link: Math.floor(Math.random() * links.length), t: Math.random(), dir: Math.random() > 0.5 ? 1 : -1, speed: 0.5 + Math.random() })),
    [packetCount, links.length],
  )
  const packetGeometry = useMemo(() => {
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(Math.max(packetCount, 1) * 3), 3))
    return g
  }, [packetCount])

  useEffect(() => {
    if (burstKey > 0) state.current.wave = clock.elapsedTime
  }, [burstKey, clock])
  useEffect(() => {
    if (mood === 'success') state.current.wave = clock.elapsedTime
  }, [mood, clock])

  useFrame(({ clock: c }, delta) => {
    const target = MOODS[mood]
    const s = state.current
    const t = c.elapsedTime
    s.speed = damp(s.speed, target.speed * (reduced ? 0.2 : 1), 2, delta)
    s.packets = damp(s.packets, target.packets, 2, delta)
    s.scale = damp(s.scale, target.scale, 2.5, delta)
    s.fall = damp(s.fall, reduced ? 0 : target.fall, 1.4, delta)
    s.links = damp(s.links, target.linkOpacity, 2, delta)
    s.rings = damp(s.rings, target.ringOpacity, 2, delta)
    s.poke = damp(s.poke, 0, 3, delta)

    const g = group.current
    if (g) {
      g.rotation.y += delta * (s.speed + s.poke * 1.5)
      const px = reduced ? 0 : pointer.y * 0.18
      const py = reduced ? 0 : pointer.x * 0.25
      g.rotation.x = damp(g.rotation.x, 0.28 + px + s.fall * 0.25, 2, delta)
      g.rotation.z = damp(g.rotation.z, -py * 0.4 + s.fall * 0.2, 2, delta)
      g.scale.setScalar(s.scale)
    }

    // Nœuds : couleur, onde de succès, effondrement en cas d'échec
    const mesh = instanced.current
    if (mesh) {
      tmp.base.set(target.node)
      const waveAge = t - s.wave
      const front = waveAge * 1.6
      for (let i = 0; i < nodes.length; i++) {
        const n = nodes[i]
        const polar = Math.acos(THREE.MathUtils.clamp(n.y / RADIUS, -1, 1))
        const w = waveAge < 3 ? Math.exp(-Math.pow(polar - front, 2) * 14) : 0
        const size = 1 + (reduced ? 0 : w * 1.8)
        tmp.p.set(n.x, n.y - s.fall * fall[i] * 0.9, n.z)
        tmp.s.setScalar(size)
        tmp.m.compose(tmp.p, tmp.q, tmp.s)
        mesh.setMatrixAt(i, tmp.m)
        mesh.getColorAt(i, tmp.cur)
        tmp.c.copy(tmp.cur).lerp(tmp.base, 1 - Math.exp(-3 * delta)).lerp(CHAMPAGNE, w)
        mesh.setColorAt(i, tmp.c)
      }
      mesh.instanceMatrix.needsUpdate = true
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
    }

    if (linkMaterial.current) linkMaterial.current.opacity = s.links
    ringMaterials.current.forEach((m, i) => {
      m.opacity = s.rings * (i === 3 ? 0.7 : 1)
      m.color.lerp(tmp.c.set(i === 3 ? target.core : '#cdb07a'), 1 - Math.exp(-2 * delta))
    })
    if (core.current) {
      const pulse = reduced ? 1 : 1 + Math.sin(t * (1.5 + s.speed * 6)) * 0.06
      core.current.scale.setScalar(0.11 * pulse * (1 + s.poke * 0.8))
      ;(core.current.material as THREE.MeshBasicMaterial).color.lerp(tmp.c.set(target.core), 1 - Math.exp(-3 * delta))
    }

    // Paquets
    const pts = packetsRef.current
    if (pts && packets.length) {
      const attr = pts.geometry.getAttribute('position') as THREE.BufferAttribute
      for (let k = 0; k < packets.length; k++) {
        const pk = packets[k]
        pk.t += delta * pk.speed * s.packets
        if (pk.t >= 1) {
          const [a, b] = links[pk.link]
          const end = pk.dir === 1 ? b : a
          const options = adjacency[end]
          pk.link = options[Math.floor(Math.random() * options.length)]
          pk.dir = links[pk.link][0] === end ? 1 : -1
          pk.t = 0
        }
        const [a, b] = links[pk.link]
        const from = nodes[pk.dir === 1 ? a : b]
        const to = nodes[pk.dir === 1 ? b : a]
        attr.setXYZ(k, from.x + (to.x - from.x) * pk.t, from.y + (to.y - from.y) * pk.t, from.z + (to.z - from.z) * pk.t)
      }
      attr.needsUpdate = true
      ;(pts.material as THREE.PointsMaterial).opacity = Math.min(1, s.packets)
    }
  })

  // Couleurs initiales des instances
  useEffect(() => {
    const mesh = instanced.current
    if (!mesh) return
    const c = new THREE.Color(MOODS.calm.node)
    for (let i = 0; i < nodes.length; i++) mesh.setColorAt(i, c)
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
  }, [nodes])

  return (
    <group
      ref={group}
      onClick={(e) => {
        e.stopPropagation()
        state.current.poke = 1
        onPoke?.()
      }}
      onPointerOver={() => (document.body.style.cursor = onPoke ? 'pointer' : '')}
      onPointerOut={() => (document.body.style.cursor = '')}
    >
      <instancedMesh ref={instanced} args={[undefined, undefined, nodes.length]}>
        <sphereGeometry args={[0.028, 10, 8]} />
        <meshBasicMaterial toneMapped={false} />
      </instancedMesh>
      <lineSegments geometry={linkGeometry}>
        <lineBasicMaterial ref={linkMaterial} color="#8fa6c3" transparent opacity={0.2} depthWrite={false} />
      </lineSegments>
      {rings.map((ring, i) => (
        <lineLoop key={i} geometry={ring.geometry} rotation={ring.rotation as unknown as THREE.Euler}>
          <lineBasicMaterial ref={(m) => { if (m) ringMaterials.current[i] = m }} color="#cdb07a" transparent opacity={0.3} depthWrite={false} />
        </lineLoop>
      ))}
      <mesh ref={core}>
        <sphereGeometry args={[1, 24, 24]} />
        <meshBasicMaterial color="#8fa6c3" transparent opacity={0.7} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
      </mesh>
      {packets.length > 0 && (
        <points ref={packetsRef} geometry={packetGeometry} frustumCulled={false}>
          <pointsMaterial color="#efe2c4" size={0.07} sizeAttenuation transparent opacity={0.5} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
        </points>
      )}
    </group>
  )
}

/** Recule la caméra dans les cadres étroits pour que la constellation ne soit jamais rognée. */
function CameraFit() {
  const { camera, size } = useThree()
  useEffect(() => {
    const aspect = size.width / Math.max(size.height, 1)
    camera.position.z = aspect >= 1 ? 6.4 : 6.4 / Math.pow(aspect, 0.85)
    camera.updateProjectionMatrix()
  }, [camera, size])
  return null
}

export default function ConstellationScene({ mood, reduced, onPoke, burstKey, onDegrade }: SceneProps & { onDegrade?: () => void }) {
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
        camera={{ position: [0, 0, 6.4], fov: 40 }}
        gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}
        onCreated={({ gl }) => gl.setClearColor(0x000000, 0)}
      >
        <PerformanceMonitor onDecline={() => setDpr(1)} flipflops={3} onFallback={() => onDegrade?.()} />
        <CameraFit />
        <Constellation mood={mood} reduced={reduced} onPoke={onPoke} burstKey={burstKey} />
      </Canvas>
    </div>
  )
}
