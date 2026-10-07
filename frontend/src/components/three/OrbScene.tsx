/**
 * Scène 3D du cristal. Chargée à la demande (lazy) : le reste de l'app ne paie pas Three.js.
 * Budget : 1 cristal (12 faces), 1 nuage de particules (un seul draw call, shader maison),
 * 1 gerbe d'étincelles (idem). DPR plafonné à 1,5 ; baisse automatique si les FPS chutent.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { PerformanceMonitor } from '@react-three/drei'
import * as THREE from 'three'
import { MOODS, type Mood } from './moods'
import { particleBudget } from '../../lib/perf'

const damp = THREE.MathUtils.damp

/* ------------------------------------------------------------------ shaders */
const auraVertex = /* glsl */ `
  uniform float uTime; uniform float uSpeed; uniform float uSpread; uniform float uRise; uniform float uPixelRatio;
  attribute float aRandom; attribute float aRadius;
  varying float vRandom; varying float vAlpha;
  void main() {
    vRandom = aRandom;
    vec3 p = position;
    float angle = uTime * uSpeed * (0.25 + aRandom * 0.75) + aRandom * 6.2831;
    float r = aRadius * uSpread;
    p.x = cos(angle) * r;
    p.z = sin(angle) * r;
    float rise = fract(aRandom * 7.0 + uTime * 0.08 * (0.5 + aRandom));
    p.y += uRise * (rise * 4.0 - 1.0);
    vAlpha = mix(1.0, 1.0 - rise, uRise);
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
    gl_PointSize = (2.0 + aRandom * 5.0 + uRise * 14.0) * uPixelRatio * (8.0 / -mv.z);
  }
`
const auraFragment = /* glsl */ `
  uniform vec3 uColorA; uniform vec3 uColorB; uniform float uGlow;
  varying float vRandom; varying float vAlpha;
  void main() {
    float d = length(gl_PointCoord - 0.5);
    float a = smoothstep(0.5, 0.0, d);
    vec3 c = mix(uColorA, uColorB, vRandom);
    gl_FragColor = vec4(c * (0.6 + uGlow * 0.6), a * vAlpha * (0.35 + uGlow * 0.4));
  }
`
const sparkVertex = /* glsl */ `
  uniform float uAge; uniform float uPixelRatio;
  attribute vec3 aDir; attribute float aSpeed; attribute float aRandom;
  varying float vAlpha; varying float vRandom;
  void main() {
    vRandom = aRandom;
    float t = max(uAge, 0.0);
    vec3 p = aDir * aSpeed * t * (1.0 - t * 0.18) - vec3(0.0, 0.9 * t * t, 0.0);
    vAlpha = uAge < 0.0 ? 0.0 : clamp(1.0 - t / 2.2, 0.0, 1.0);
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
    gl_PointSize = (3.0 + aRandom * 6.0) * uPixelRatio * (8.0 / -mv.z);
  }
`
const sparkFragment = /* glsl */ `
  varying float vAlpha; varying float vRandom;
  void main() {
    vec2 uv = gl_PointCoord - 0.5;
    float star = max(0.0, 1.0 - (abs(uv.x) + abs(uv.y)) * 2.2) + smoothstep(0.5, 0.0, length(uv)) * 0.6;
    vec3 gold = vec3(0.96, 0.87, 0.65); vec3 violet = vec3(0.65, 0.55, 0.98); vec3 cyan = vec3(0.37, 0.92, 0.83);
    vec3 c = vRandom < 0.5 ? mix(gold, violet, vRandom * 2.0) : mix(violet, cyan, (vRandom - 0.5) * 2.0);
    gl_FragColor = vec4(c, star * vAlpha);
  }
`

/* ------------------------------------------------------------------ éléments */
interface SceneProps { mood: Mood; reduced: boolean; onPoke?: () => void; burstKey: number }

function Crystal({ mood, reduced, onPoke }: SceneProps) {
  const group = useRef<THREE.Group>(null)
  const material = useRef<THREE.MeshStandardMaterial>(null)
  const edges = useRef<THREE.LineBasicMaterial>(null)
  const core = useRef<THREE.Mesh>(null)
  const state = useRef({ speed: 0.2, glow: 0.5, droop: 0, poke: 0 })
  const geometry = useMemo(() => {
    const g = new THREE.OctahedronGeometry(1, 0)
    g.scale(0.9, 1.45, 0.9)
    return g
  }, [])
  const edgeGeometry = useMemo(() => new THREE.EdgesGeometry(geometry), [geometry])
  const emissive = useMemo(() => new THREE.Color(), [])

  useFrame(({ clock }, delta) => {
    const target = MOODS[mood]
    const s = state.current
    const t = clock.elapsedTime
    s.speed = damp(s.speed, target.speed * (reduced ? 0.15 : 1), 2.5, delta)
    s.glow = damp(s.glow, target.glow, 3, delta)
    s.droop = damp(s.droop, target.droop, 1.8, delta)
    s.poke = damp(s.poke, 0, 4, delta)
    if (group.current) {
      group.current.rotation.y += delta * (s.speed + s.poke * 6)
      group.current.rotation.z = s.droop * 0.9
      group.current.rotation.x = reduced ? 0 : Math.sin(t * 0.35) * 0.12
      group.current.position.y = (reduced ? 0 : Math.sin(t * 0.9) * 0.08 * (1 - s.droop * 2)) - s.droop * 0.6
      const scale = 1 + s.poke * 0.12
      group.current.scale.setScalar(scale)
    }
    if (material.current) {
      emissive.set(target.emissive)
      material.current.emissive.lerp(emissive, 1 - Math.exp(-3 * delta))
      material.current.emissiveIntensity = 0.6 + s.glow * 0.9
    }
    if (edges.current) edges.current.opacity = 0.25 + s.glow * 0.45
    if (core.current) {
      const pulse = reduced ? 1 : 1 + Math.sin(t * (2 + s.speed * 3)) * 0.08
      core.current.scale.setScalar((0.25 + s.glow * 0.18) * pulse)
      ;(core.current.material as THREE.MeshBasicMaterial).color.set(target.colorA)
    }
  })

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
      <mesh geometry={geometry}>
        <meshStandardMaterial ref={material} color="#22164d" metalness={0.35} roughness={0.18} flatShading transparent opacity={0.88} />
      </mesh>
      <lineSegments geometry={edgeGeometry}>
        <lineBasicMaterial ref={edges} color="#f5dfa5" transparent opacity={0.5} />
      </lineSegments>
      <mesh ref={core}>
        <sphereGeometry args={[1, 16, 16]} />
        <meshBasicMaterial color="#f5dfa5" transparent opacity={0.9} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
    </group>
  )
}

function Aura({ mood, reduced }: SceneProps) {
  const count = useMemo(() => particleBudget(700), [])
  const { gl } = useThree()
  const material = useRef<THREE.ShaderMaterial>(null)
  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry()
    const positions = new Float32Array(count * 3)
    const randoms = new Float32Array(count)
    const radii = new Float32Array(count)
    for (let i = 0; i < count; i++) {
      randoms[i] = Math.random()
      radii[i] = 1.5 + Math.pow(Math.random(), 0.7) * 1.9
      positions[i * 3 + 1] = (Math.random() - 0.5) * 2.6
    }
    g.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    g.setAttribute('aRandom', new THREE.BufferAttribute(randoms, 1))
    g.setAttribute('aRadius', new THREE.BufferAttribute(radii, 1))
    return g
  }, [count])
  const uniforms = useMemo(() => ({
    uTime: { value: 0 }, uSpeed: { value: 0.2 }, uSpread: { value: 1 }, uRise: { value: 0 }, uGlow: { value: 0.5 },
    uPixelRatio: { value: Math.min(gl.getPixelRatio(), 1.5) },
    uColorA: { value: new THREE.Color('#a78bfa') }, uColorB: { value: new THREE.Color('#5eead4') },
  }), [gl])
  const tmpA = useMemo(() => new THREE.Color(), [])
  const tmpB = useMemo(() => new THREE.Color(), [])

  useFrame((_, delta) => {
    const target = MOODS[mood]
    const u = uniforms
    u.uTime.value += delta * (reduced ? 0.15 : 1)
    u.uSpeed.value = damp(u.uSpeed.value, target.speed * 1.4, 2, delta)
    u.uSpread.value = damp(u.uSpread.value, target.spread, 2, delta)
    u.uRise.value = damp(u.uRise.value, reduced ? 0 : target.rise, 1.5, delta)
    u.uGlow.value = damp(u.uGlow.value, target.glow, 2.5, delta)
    u.uColorA.value.lerp(tmpA.set(target.colorA), 1 - Math.exp(-2.5 * delta))
    u.uColorB.value.lerp(tmpB.set(target.colorB), 1 - Math.exp(-2.5 * delta))
  })

  return (
    <points geometry={geometry}>
      <shaderMaterial ref={material} uniforms={uniforms} vertexShader={auraVertex} fragmentShader={auraFragment}
        transparent depthWrite={false} blending={THREE.AdditiveBlending} />
    </points>
  )
}

function Sparks({ burstKey, reduced }: SceneProps) {
  const count = useMemo(() => particleBudget(420), [])
  const { gl } = useThree()
  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry()
    const dirs = new Float32Array(count * 3)
    const speeds = new Float32Array(count)
    const randoms = new Float32Array(count)
    for (let i = 0; i < count; i++) {
      const v = new THREE.Vector3().randomDirection()
      dirs.set([v.x, v.y * 0.8 + 0.35, v.z], i * 3)
      speeds[i] = 1.2 + Math.random() * 2.8
      randoms[i] = Math.random()
    }
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(count * 3), 3))
    g.setAttribute('aDir', new THREE.BufferAttribute(dirs, 3))
    g.setAttribute('aSpeed', new THREE.BufferAttribute(speeds, 1))
    g.setAttribute('aRandom', new THREE.BufferAttribute(randoms, 1))
    return g
  }, [count])
  const uniforms = useMemo(() => ({ uAge: { value: -1 }, uPixelRatio: { value: Math.min(gl.getPixelRatio(), 1.5) } }), [gl])
  const started = useRef<number | null>(null)
  const clock = useThree((s) => s.clock)

  useEffect(() => {
    if (burstKey > 0 && !reduced) started.current = clock.elapsedTime
  }, [burstKey, reduced, clock])

  useFrame(({ clock: c }) => {
    uniforms.uAge.value = started.current === null ? -1 : c.elapsedTime - started.current
    if (uniforms.uAge.value > 2.5) started.current = null
  })

  return (
    <points geometry={geometry} frustumCulled={false}>
      <shaderMaterial uniforms={uniforms} vertexShader={sparkVertex} fragmentShader={sparkFragment}
        transparent depthWrite={false} blending={THREE.AdditiveBlending} />
    </points>
  )
}

function Lights({ mood }: { mood: Mood }) {
  const key = useRef<THREE.PointLight>(null)
  const tmp = useMemo(() => new THREE.Color(), [])
  useFrame((_, delta) => {
    if (key.current) key.current.color.lerp(tmp.set(MOODS[mood].colorA), 1 - Math.exp(-2 * delta))
  })
  return (
    <>
      <ambientLight intensity={0.35} />
      <pointLight ref={key} position={[3, 3, 4]} intensity={40} distance={20} />
      <pointLight position={[-4, -2, 2]} intensity={18} color="#5eead4" distance={20} />
      <pointLight position={[0, 4, -3]} intensity={22} color="#e8c77a" distance={20} />
    </>
  )
}

/* ------------------------------------------------------------------ canvas */
export default function OrbScene({
  mood, reduced, onPoke, burstKey, onDegrade,
}: SceneProps & { onDegrade?: () => void }) {
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
        camera={{ position: [0, 0, 6.2], fov: 40 }}
        gl={{ antialias: false, alpha: true, powerPreference: 'high-performance' }}
        onCreated={({ gl }) => gl.setClearColor(0x000000, 0)}
      >
        <PerformanceMonitor
          onDecline={() => setDpr(1)}
          flipflops={3}
          onFallback={() => onDegrade?.()}
        />
        <Lights mood={mood} />
        <Crystal mood={mood} reduced={reduced} onPoke={onPoke} burstKey={burstKey} />
        <Aura mood={mood} reduced={reduced} burstKey={burstKey} />
        <Sparks mood={mood} reduced={reduced} burstKey={burstKey} />
      </Canvas>
    </div>
  )
}
