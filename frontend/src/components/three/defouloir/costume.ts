/**
 * Déguisements sur mesure pour la tête de RFPascontente : perruques, moustaches, barbes, lunettes, chapeaux, nez, cou.
 * Tout est construit en primitives three.js (aucun fichier), dans le repère du pivot (base du cou).
 * Repères anatomiques mesurés sur le maillage mis à l'échelle (sommet 2,70 ; nez 2,10 ; yeux 2,17 ; lèvre 2,04 ; menton 1,86).
 */
import * as THREE from 'three'
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js'

export type Slot = 'cheveux' | 'chapeau' | 'lunettes' | 'moustache' | 'barbe' | 'nez' | 'cou'
export const SLOTS: Slot[] = ['cheveux', 'chapeau', 'lunettes', 'moustache', 'barbe', 'nez', 'cou']
export interface SlotStyle { item: string | null; color: string; size: number }
export type Costume = Record<Slot, SlotStyle>

/** Objets par emplacement, avec leur couleur par défaut. */
export const ITEMS: Record<Slot, { id: string; color: string }[]> = {
  cheveux: [{ id: 'afro', color: '#2b1a10' }, { id: 'crete', color: '#ff3d7f' }, { id: 'carre', color: '#1b1530' }, { id: 'longs', color: '#f2c14e' }, { id: 'clown', color: '#ff7b00' }],
  chapeau: [{ id: 'haut', color: '#1b1530' }, { id: 'fete', color: '#9b5de5' }, { id: 'couronne', color: '#ffd23f' }, { id: 'casquette', color: '#4cc9f0' }, { id: 'viking', color: '#9aa1ad' }],
  lunettes: [{ id: 'rondes', color: '#1b1530' }, { id: 'soleil', color: '#1b1530' }, { id: 'etoiles', color: '#ff3d7f' }, { id: 'monocle', color: '#d4af37' }],
  moustache: [{ id: 'guidon', color: '#2b1a10' }, { id: 'morse', color: '#5a3a22' }, { id: 'dali', color: '#1b1530' }, { id: 'chevron', color: '#6b4226' }],
  barbe: [{ id: 'bouc', color: '#2b1a10' }, { id: 'pleine', color: '#5a3a22' }, { id: 'noel', color: '#ffffff' }],
  nez: [{ id: 'clown', color: '#e63946' }, { id: 'pinocchio', color: '#c68b59' }],
  cou: [{ id: 'noeud', color: '#e63946' }, { id: 'cravate', color: '#4cc9f0' }, { id: 'perles', color: '#fff8ee' }],
}

export const EMPTY: Costume = Object.fromEntries(SLOTS.map((s) => [s, { item: null, color: ITEMS[s][0].color, size: 1 }])) as Costume

export function randomCostume(): Costume {
  const out = { ...EMPTY }
  for (const s of SLOTS) {
    const keep = s === 'cheveux' || s === 'chapeau' || Math.random() < 0.6
    const it = ITEMS[s][Math.floor(Math.random() * ITEMS[s].length)]
    out[s] = { item: keep ? it.id : null, color: it.color, size: 1 }
  }
  if (out.chapeau.item && out.cheveux.item && Math.random() < 0.5) out.cheveux = { ...out.cheveux, item: null }
  return out
}

// ------------------------------------------------------------------ repères (repère monde au repos ; pivot à y = 1)
const PIVOT_Y = 1
const L = (x: number, y: number, z: number) => new THREE.Vector3(x, y - PIVOT_Y, z)
const SKULL = { c: L(0, 2.36, 0.02), r: new THREE.Vector3(0.32, 0.34, 0.44) }
const ANCHORS: Record<Slot, THREE.Vector3> = {
  cheveux: L(0, 2.4, 0.02), chapeau: L(0, 2.64, 0), lunettes: L(0, 2.17, 0.46), moustache: L(0, 2.035, 0.5),
  barbe: L(0, 1.88, 0.44), nez: L(0, 2.1, 0.55), cou: L(0, 1.46, 0.14),
}

/** Point de la calotte (ellipsoïde) : theta depuis le sommet, phi depuis l'avant (+z). */
function skull(theta: number, phi: number, k = 1) {
  const { c, r } = SKULL
  return new THREE.Vector3(c.x + r.x * k * Math.sin(theta) * Math.sin(phi), c.y + r.y * k * Math.cos(theta), c.z + r.z * k * Math.sin(theta) * Math.cos(phi))
}
function skullNormal(p: THREE.Vector3) {
  const { c, r } = SKULL
  return new THREE.Vector3((p.x - c.x) / (r.x * r.x), (p.y - c.y) / (r.y * r.y), (p.z - c.z) / (r.z * r.z)).normalize()
}

const mat = (color: string, extra: THREE.MeshStandardMaterialParameters = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.6, ...extra })
const hairMat = (color: string) => mat(color, { roughness: 0.95 })
const at = (g: THREE.BufferGeometry, p: THREE.Vector3, q?: THREE.Quaternion, s?: THREE.Vector3) => {
  const m = new THREE.Matrix4().compose(p, q ?? new THREE.Quaternion(), s ?? new THREE.Vector3(1, 1, 1))
  return g.applyMatrix4(m)
}
const along = (dir: THREE.Vector3) => new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.clone().normalize())
function mesh(geos: THREE.BufferGeometry[], material: THREE.Material) {
  const clean = geos.map((g) => (g.index ? g.toNonIndexed() : g)).map((g) => { for (const k of Object.keys(g.attributes)) if (!['position', 'normal', 'uv'].includes(k)) g.deleteAttribute(k); return g })
  const merged = mergeGeometries(clean) ?? clean[0]
  const m = new THREE.Mesh(merged, material)
  m.castShadow = true
  return m
}
/** Calotte ellipsoïdale (sphère unité mise à l'échelle), avec éventuellement une fenêtre pour le visage. */
function shell(k: number, t0: number, t1: number, faceWindow = 0) {
  const phiStart = Math.PI / 2 + faceWindow
  const g = new THREE.SphereGeometry(1, 48, 24, phiStart, Math.PI * 2 - faceWindow * 2, t0, t1 - t0)
  return at(g, SKULL.c, undefined, SKULL.r.clone().multiplyScalar(k))
}
function fibonacci(n: number) {
  const pts: [number, number][] = []
  const golden = Math.PI * (3 - Math.sqrt(5))
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1)) * 2
    pts.push([Math.acos(y), (i * golden) % (Math.PI * 2)])
  }
  return pts
}
function flipWinding(g: THREE.BufferGeometry) {
  const index = g.index
  if (index) {
    for (let i = 0; i < index.count; i += 3) { const b = index.getX(i + 1); index.setX(i + 1, index.getX(i + 2)); index.setX(i + 2, b) }
    index.needsUpdate = true
  }
  return g
}
/** Moitié gauche = miroir de la droite (ordre des sommets inversé pour garder les faces visibles). */
const side = (geos: THREE.BufferGeometry[]) => geos.flatMap((g) => [g, flipWinding(g.clone().applyMatrix4(new THREE.Matrix4().makeScale(-1, 1, 1)))])
function tube(points: [number, number, number][], radius: number, origin: THREE.Vector3) {
  const curve = new THREE.CatmullRomCurve3(points.map(([x, y, z]) => new THREE.Vector3(x, y, z).add(origin)))
  return new THREE.TubeGeometry(curve, 32, radius, 8, false)
}
function stripes(a: string, b: string) {
  const c = document.createElement('canvas')
  c.width = 64
  c.height = 256
  const g = c.getContext('2d')!
  for (let i = 0; i < 8; i++) { g.fillStyle = i % 2 ? a : b; g.fillRect(0, i * 32, 64, 32) }
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  return t
}
function starShape(outer: number, inner: number) {
  const s = new THREE.Shape()
  for (let i = 0; i < 10; i++) {
    const r = i % 2 ? inner : outer
    const a = (i / 10) * Math.PI * 2 + Math.PI / 2
    if (i === 0) s.moveTo(Math.cos(a) * r, Math.sin(a) * r)
    else s.lineTo(Math.cos(a) * r, Math.sin(a) * r)
  }
  return s
}

// ------------------------------------------------------------------ fabrication
function build(slot: Slot, item: string, color: string): THREE.Object3D {
  const g = new THREE.Group()
  const add = (...o: THREE.Object3D[]) => { g.add(...o); return g }
  switch (`${slot}:${item}`) {
    // ---------------- cheveux
    case 'cheveux:afro': {
      const geos = fibonacci(150).filter(([t, p]) => {
        const front = Math.abs(((p + Math.PI) % (Math.PI * 2)) - Math.PI) < 1.0
        return t < (front ? 0.38 * Math.PI : 0.68 * Math.PI)
      }).map(([t, p]) => at(new THREE.IcosahedronGeometry(0.1 + Math.random() * 0.04, 2), skull(t, p, 1.18)))
      return add(mesh(geos, hairMat(color)))
    }
    case 'cheveux:crete': {
      const geos = []
      for (let a = -0.62 * Math.PI; a <= 0.36 * Math.PI; a += 0.075 * Math.PI) {
        const p = skull(Math.abs(a), a >= 0 ? 0 : Math.PI, 0.98)
        const n = skullNormal(p)
        const h = 0.26 + 0.1 * Math.cos(a * 1.2)
        geos.push(at(new THREE.ConeGeometry(0.06, h, 10), p.clone().addScaledVector(n, h / 2), along(n)))
      }
      return add(mesh(geos, hairMat(color)))
    }
    case 'cheveux:carre': {
      const m = hairMat(color)
      m.side = THREE.DoubleSide
      return add(mesh([shell(1.07, 0, 0.36 * Math.PI), shell(1.07, 0.36 * Math.PI, 0.7 * Math.PI, 0.95)], m))
    }
    case 'cheveux:longs': {
      const m = hairMat(color)
      m.side = THREE.DoubleSide
      const back = at(new THREE.CylinderGeometry(0.36, 0.46, 0.75, 32, 1, true, Math.PI * 0.62, Math.PI * 0.76), L(0, 1.9, -0.04), undefined, new THREE.Vector3(1, 1, 1.15))
      return add(mesh([shell(1.07, 0, 0.36 * Math.PI), shell(1.07, 0.36 * Math.PI, 0.78 * Math.PI, 0.9), back], m))
    }
    case 'cheveux:clown': {
      const geos: THREE.BufferGeometry[] = []
      for (const sx of [-1, 1]) {
        for (const [t, p] of fibonacci(26)) {
          const c = L(sx * 0.37, 2.3, -0.06).add(new THREE.Vector3(Math.sin(t) * Math.sin(p), Math.cos(t), Math.sin(t) * Math.cos(p)).multiplyScalar(0.12))
          geos.push(at(new THREE.IcosahedronGeometry(0.075, 1), c))
        }
      }
      return add(mesh(geos, hairMat(color)))
    }
    // ---------------- chapeaux
    case 'chapeau:haut': {
      const base = L(0, 2.62, -0.02)
      add(mesh([at(new THREE.CylinderGeometry(0.44, 0.44, 0.025, 48), base), at(new THREE.CylinderGeometry(0.28, 0.27, 0.46, 40), base.clone().add(new THREE.Vector3(0, 0.24, 0)))], mat(color, { roughness: 0.5 })))
      add(mesh([at(new THREE.CylinderGeometry(0.285, 0.285, 0.07, 40), base.clone().add(new THREE.Vector3(0, 0.06, 0)))], mat('#e63946')))
      g.userData.tilt = [0, 0, -0.08]
      return g
    }
    case 'chapeau:fete': {
      const cone = new THREE.Mesh(at(new THREE.ConeGeometry(0.17, 0.48, 40), L(0, 2.86, 0.02)), new THREE.MeshStandardMaterial({ map: stripes(color, '#ffd23f'), roughness: 0.6 }))
      cone.castShadow = true
      add(cone, mesh([at(new THREE.IcosahedronGeometry(0.05, 2), L(0, 3.11, 0.02))], mat('#ffffff', { roughness: 1 })))
      g.userData.tilt = [0.12, 0, 0.22]
      return g
    }
    case 'chapeau:couronne': {
      const gold = mat(color, { metalness: 1, roughness: 0.25, side: THREE.DoubleSide })
      const geos = [at(new THREE.CylinderGeometry(0.31, 0.3, 0.13, 48, 1, true), L(0, 2.62, -0.02))]
      for (let i = 0; i < 8; i++) {
        const a = (i / 8) * Math.PI * 2
        geos.push(at(new THREE.ConeGeometry(0.045, 0.13, 8), L(Math.sin(a) * 0.305, 2.745, -0.02 + Math.cos(a) * 0.305)))
      }
      add(mesh(geos, gold))
      const gems = [0, 1, 2, 3].map((i) => at(new THREE.IcosahedronGeometry(0.025, 1), L(Math.sin(i * Math.PI / 2) * 0.315, 2.62, -0.02 + Math.cos(i * Math.PI / 2) * 0.315)))
      return add(mesh(gems, mat('#e63946', { roughness: 0.1, metalness: 0.3 })))
    }
    case 'chapeau:casquette': {
      const m = mat(color, { side: THREE.DoubleSide })
      const visor = at(new THREE.CylinderGeometry(0.3, 0.3, 0.02, 32, 1, false, -Math.PI * 0.3, Math.PI * 0.6), L(0, 2.47, 0.22), new THREE.Quaternion().setFromEuler(new THREE.Euler(0.12, 0, 0)), new THREE.Vector3(1, 1.4, 1.45))
      add(mesh([shell(1.08, 0, 0.47 * Math.PI), visor], m))
      return add(mesh([at(new THREE.IcosahedronGeometry(0.03, 1), L(0, 2.72, 0.02))], mat('#ffffff')))
    }
    case 'chapeau:viking': {
      const metal = mat(color, { metalness: 0.8, roughness: 0.35, side: THREE.DoubleSide })
      add(mesh([shell(1.1, 0, 0.56 * Math.PI)], metal))
      add(mesh([at(new THREE.TorusGeometry(1, 0.035, 10, 64), new THREE.Vector3(0, SKULL.c.y + SKULL.r.y * 1.1 * Math.cos(0.56 * Math.PI), SKULL.c.z), new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.PI / 2, 0, 0)), new THREE.Vector3(SKULL.r.x * 1.1, SKULL.r.z * 1.1, 1))], mat('#c9a227', { metalness: 1, roughness: 0.3 })))
      const horns = side([at(new THREE.ConeGeometry(0.065, 0.34, 16), L(0.42, 2.52, 0.02), new THREE.Quaternion().setFromEuler(new THREE.Euler(0, 0, -0.75)))])
      return add(mesh(horns, mat('#fff3dc', { roughness: 0.5 })))
    }
    // ---------------- lunettes
    case 'lunettes:rondes':
    case 'lunettes:soleil': {
      const r = item === 'soleil' ? 0.075 : 0.065
      const frame = mat(color, { roughness: 0.3, metalness: 0.4 })
      const ring = (x: number) => at(new THREE.TorusGeometry(r, 0.009, 10, 36), L(x, 2.17, 0.475))
      const arm = (sx: number) => at(new THREE.CylinderGeometry(0.007, 0.007, 0.42, 6), L(sx * 0.29, 2.18, 0.26), new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.PI / 2, 0, 0)).premultiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(0, sx * 0.32, 0))))
      add(mesh([ring(0.105), ring(-0.105), at(new THREE.TorusGeometry(0.03, 0.007, 8, 16, Math.PI), L(0, 2.18, 0.485)), arm(1), arm(-1)], frame))
      const lens = new THREE.MeshStandardMaterial({ color: item === 'soleil' ? '#111111' : '#dff6ff', transparent: true, opacity: item === 'soleil' ? 0.88 : 0.25, roughness: 0.05, metalness: 0.2 })
      return add(mesh([at(new THREE.CircleGeometry(r, 32), L(0.105, 2.17, 0.474)), at(new THREE.CircleGeometry(r, 32), L(-0.105, 2.17, 0.474))], lens))
    }
    case 'lunettes:etoiles': {
      const ex = new THREE.ExtrudeGeometry(starShape(0.1, 0.05), { depth: 0.02, bevelEnabled: false })
      const left = ex.clone().translate(-0.11, 2.18 - PIVOT_Y, 0.47)
      const right = ex.clone().translate(0.11, 2.18 - PIVOT_Y, 0.47)
      const m = new THREE.Mesh(mergeGeometries([left, right])!, mat(color, { roughness: 0.3 }))
      m.castShadow = true
      add(m)
      return add(mesh([at(new THREE.CircleGeometry(0.045, 24), L(0.11, 2.18, 0.492)), at(new THREE.CircleGeometry(0.045, 24), L(-0.11, 2.18, 0.492))], new THREE.MeshStandardMaterial({ color: '#111', transparent: true, opacity: 0.8 })))
    }
    case 'lunettes:monocle': {
      const goldm = mat(color, { metalness: 1, roughness: 0.25 })
      add(mesh([at(new THREE.TorusGeometry(0.07, 0.008, 10, 36), L(0.105, 2.17, 0.48)), tube([[0.105, -0.07, 0.0], [0.14, -0.2, 0.02], [0.18, -0.35, -0.02], [0.2, -0.45, -0.08]], 0.004, L(0, 2.17, 0.48))], goldm))
      return add(mesh([at(new THREE.CircleGeometry(0.07, 32), L(0.105, 2.17, 0.479))], new THREE.MeshStandardMaterial({ color: '#dff6ff', transparent: true, opacity: 0.3 })))
    }
    // ---------------- moustaches
    case 'moustache:guidon':
      return add(mesh(side([tube([[0, 0, 0.012], [0.04, -0.004, 0.006], [0.085, -0.012, -0.006], [0.125, -0.002, -0.022], [0.155, 0.03, -0.03], [0.145, 0.062, -0.03], [0.122, 0.05, -0.026]], 0.017, ANCHORS.moustache)]), hairMat(color)))
    case 'moustache:morse': {
      const pieces = side([at(new THREE.CapsuleGeometry(0.036, 0.11, 6, 12), ANCHORS.moustache.clone().add(new THREE.Vector3(0.058, -0.03, -0.008)), new THREE.Quaternion().setFromEuler(new THREE.Euler(0, 0.35, Math.PI / 2 + 0.5)), new THREE.Vector3(1, 1, 0.75))])
      return add(mesh(pieces, hairMat(color)))
    }
    case 'moustache:dali':
      return add(mesh(side([tube([[0, 0, 0.012], [0.06, -0.002, 0.004], [0.12, 0.012, -0.014], [0.17, 0.05, -0.02], [0.2, 0.11, -0.02], [0.21, 0.15, -0.018]], 0.009, ANCHORS.moustache)]), hairMat(color)))
    case 'moustache:chevron': {
      const pieces = side([at(new THREE.CapsuleGeometry(0.03, 0.1, 6, 12), ANCHORS.moustache.clone().add(new THREE.Vector3(0.055, -0.015, -0.006)), new THREE.Quaternion().setFromEuler(new THREE.Euler(0, 0.3, Math.PI / 2 - 0.25)), new THREE.Vector3(1, 1, 0.7))])
      return add(mesh(pieces, hairMat(color)))
    }
    // ---------------- barbes
    case 'barbe:bouc':
      return add(mesh([at(new THREE.ConeGeometry(0.055, 0.14, 16), L(0, 1.8, 0.47), new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.PI - 0.25, 0, 0))), at(new THREE.SphereGeometry(0.055, 16, 12), L(0, 1.87, 0.475), undefined, new THREE.Vector3(1, 0.8, 0.6))], hairMat(color)))
    case 'barbe:pleine':
    case 'barbe:noel': {
      const m = hairMat(color)
      m.side = THREE.DoubleSide
      const geos: THREE.BufferGeometry[] = [at(new THREE.SphereGeometry(1, 40, 20, Math.PI / 2 - 1.5, 3.0, 0.5 * Math.PI, 0.42 * Math.PI), L(0, 2.06, 0.05), undefined, new THREE.Vector3(0.33, 0.3, 0.46))]
      if (item === 'noel') geos.push(at(new THREE.ConeGeometry(0.2, 0.42, 24), L(0, 1.63, 0.36), new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.PI - 0.3, 0, 0)), new THREE.Vector3(1.2, 1, 0.6)))
      return add(mesh(geos, m))
    }
    // ---------------- nez
    case 'nez:clown':
      return add(mesh([at(new THREE.SphereGeometry(0.065, 32, 20), L(0, 2.1, 0.575))], mat(color, { roughness: 0.15 })))
    case 'nez:pinocchio':
      return add(mesh([at(new THREE.ConeGeometry(0.03, 0.36, 16), L(0, 2.1, 0.72), new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.PI / 2, 0, 0)))], mat(color, { roughness: 0.8 })))
    // ---------------- cou
    case 'cou:noeud': {
      const c = ANCHORS.cou
      const wings = side([at(new THREE.ConeGeometry(0.06, 0.11, 4), c.clone().add(new THREE.Vector3(0.055, 0, 0.01)), new THREE.Quaternion().setFromEuler(new THREE.Euler(0, 0, Math.PI / 2)), new THREE.Vector3(1, 1, 0.45))])
      return add(mesh([...wings, at(new THREE.SphereGeometry(0.025, 12, 8), c.clone().add(new THREE.Vector3(0, 0, 0.02)))], mat(color, { roughness: 0.5 })))
    }
    case 'cou:cravate': {
      const s = new THREE.Shape([new THREE.Vector2(-0.03, 0), new THREE.Vector2(0.03, 0), new THREE.Vector2(0.02, -0.05), new THREE.Vector2(0.05, -0.33), new THREE.Vector2(0, -0.39), new THREE.Vector2(-0.05, -0.33), new THREE.Vector2(-0.02, -0.05)])
      const geo = new THREE.ExtrudeGeometry(s, { depth: 0.015, bevelEnabled: false })
      const m = new THREE.Mesh(geo, mat(color, { roughness: 0.5 }))
      m.position.copy(ANCHORS.cou).add(new THREE.Vector3(0, 0.0, 0.0))
      m.rotation.x = -0.32
      m.castShadow = true
      return add(m)
    }
    case 'cou:perles': {
      const geos = []
      for (let i = 0; i < 30; i++) {
        const a = (i / 30) * Math.PI * 2
        const front = Math.cos(a)
        geos.push(at(new THREE.SphereGeometry(0.022, 12, 8), L(Math.sin(a) * 0.27, 1.43 - 0.05 * Math.max(front, 0), -0.13 + front * 0.3)))
      }
      return add(mesh(geos, mat(color, { roughness: 0.15, metalness: 0.1 })))
    }
  }
  return g
}

/** Accessoire prêt à poser sur le pivot : la taille se règle autour de son point d'ancrage. */
export function accessory(slot: Slot, style: SlotStyle): THREE.Object3D | null {
  if (!style.item) return null
  const inner = build(slot, style.item, style.color)
  const anchor = ANCHORS[slot]
  const outer = new THREE.Group()
  outer.position.copy(anchor)
  inner.position.sub(anchor)
  outer.add(inner)
  outer.scale.setScalar(style.size)
  const tilt = inner.userData.tilt as [number, number, number] | undefined
  if (tilt) outer.rotation.set(...tilt)
  outer.userData.slot = slot
  outer.traverse((o) => { o.userData.slot = slot })
  return outer
}

const dress = (parts: Partial<Record<Slot, string>>): Costume =>
  Object.fromEntries(SLOTS.map((s) => {
    const id = parts[s] ?? null
    return [s, { item: id, color: (ITEMS[s].find((i) => i.id === id) ?? ITEMS[s][0]).color, size: 1 }]
  })) as Costume

/** Tenue de départ (modifiable, mémorisée dans le navigateur). */
export const DEFAULT_COSTUME: Costume = dress({ chapeau: 'fete', lunettes: 'etoiles', nez: 'clown', cou: 'perles' })
