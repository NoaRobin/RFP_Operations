/**
 * Cockpit QviAPI : la bibliothèque en constellation 3D. Un point par texte (taille = utilisations, couleur = thème),
 * répartis sur une sphère qui tourne lentement ; elle se déploie à l'arrivée (GSAP). Décoratif : les chiffres restent
 * dans les panneaux à côté. Jamais affichée en mouvement réduit ni sans WebGL.
 */
import { useEffect, useMemo, useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { gsap } from '../../motion/gsap'

const PALETTE = ['#4493f8', '#768390', '#9198a1', '#3fb950', '#ab7df8', '#56a3ff']

function hash(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0
  return Math.abs(h)
}

function Stars({ items }: { items: { group: string; times_used: number }[] }) {
  const points = useRef<THREE.Points>(null)
  const { geometry, material } = useMemo(() => {
    const n = Math.max(1, items.length)
    const pos = new Float32Array(n * 3)
    const col = new Float32Array(n * 3)
    const size = new Float32Array(n)
    const max = Math.max(1, ...items.map((x) => x.times_used))
    const golden = Math.PI * (3 - Math.sqrt(5))
    items.forEach((it, i) => {
      const y = 1 - (i / Math.max(1, n - 1)) * 2
      const r = Math.sqrt(1 - y * y)
      const t = golden * i
      const R = 2.1 + (hash(it.group + i) % 100) / 400
      pos.set([Math.cos(t) * r * R, y * R, Math.sin(t) * r * R], i * 3)
      const c = new THREE.Color(PALETTE[hash(it.group) % PALETTE.length])
      col.set([c.r, c.g, c.b], i * 3)
      size[i] = 3 + 10 * Math.log1p(it.times_used) / Math.log1p(max)
    })
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    g.setAttribute('color', new THREE.BufferAttribute(col, 3))
    g.setAttribute('size', new THREE.BufferAttribute(size, 1))
    const m = new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, vertexColors: true,
      vertexShader: 'attribute float size; varying vec3 vColor; void main(){ vColor = color; vec4 mv = modelViewMatrix * vec4(position,1.0); gl_PointSize = size * (3.0 / -mv.z); gl_Position = projectionMatrix * mv; }',
      fragmentShader: 'varying vec3 vColor; void main(){ float d = length(gl_PointCoord - 0.5); float a = smoothstep(0.5, 0.0, d); gl_FragColor = vec4(vColor, a * 0.75); }',
    })
    return { geometry: g, material: m }
  }, [items])
  useEffect(() => () => { geometry.dispose(); material.dispose() }, [geometry, material])
  useEffect(() => {
    if (!points.current) return
    const tw = gsap.fromTo(points.current.scale, { x: 0.05, y: 0.05, z: 0.05 }, { x: 1, y: 1, z: 1, duration: 1.8, ease: 'expo.out' })
    return () => { tw.kill() }
  }, [])
  useFrame((state, dt) => {
    if (!points.current) return
    points.current.rotation.y += dt * 0.05
    points.current.rotation.x = THREE.MathUtils.lerp(points.current.rotation.x, state.pointer.y * 0.08, 0.04)
  })
  return <points ref={points} geometry={geometry} material={material} />
}

export default function Constellation({ items }: { items: { group: string; times_used: number }[] }) {
  return (
    <div className="pointer-events-none h-40 w-full" aria-hidden="true">
      <Canvas dpr={[1, 1.6]} camera={{ position: [0, 0, 6], fov: 45 }} gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}>
        <Stars items={items} />
      </Canvas>
    </div>
  )
}
