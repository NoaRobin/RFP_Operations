/**
 * RFPascontente : le défouloir 3D. Une tête scannée (exemple « decals » de three.js), et tout un arsenal à lui lancer.
 * - Taches : décalcomanies projetées sur le vrai maillage (DecalGeometry), accrochées à la tête (elles suivent ses mouvements).
 * - Physique : cannon-es (objets qui rebondissent, s'empilent ; verres et tasses qui éclatent en morceaux).
 * - Impacts précis : chaque objet est suivi par lancer de rayon entre deux images (pas de traversée à grande vitesse).
 * - Sons synthétisés (Web Audio, aucun fichier), coupables. En mouvement réduit : ni secousse, ni gouttelettes.
 */
import * as THREE from 'three'
import * as CANNON from 'cannon-es'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { DecalGeometry } from 'three/examples/jsm/geometries/DecalGeometry.js'
import { accessory, SLOTS, type Costume, type Slot } from './costume'
import { Sounds } from './sounds'

export type Weapon = 'peinture' | 'verre' | 'tomate' | 'oeuf' | 'tarte' | 'tasse' | 'classeur' | 'melon'
export const WEAPONS: Weapon[] = ['peinture', 'verre', 'tomate', 'oeuf', 'tarte', 'tasse', 'classeur', 'melon']
export type Character = 'homme' | 'femme'
export interface Shape { height: number; build: number; head: number }
export const DEFAULT_SHAPE: Shape = { height: 1, build: 1, head: 1 }
const FEMME_H = 1.72 // taille de base du personnage en pied (m)
// Repère de la tête du bonhomme (pivot) sur lequel les accessoires ont été dessinés : centre et hauteur menton → sommet
const LEE_HEAD_CENTER = new THREE.Vector3(0, 1.225, 0.02)
const LEE_HEAD_HEIGHT = 0.95
export const RAINBOW = 'arc-en-ciel'
const PALETTE = ['#ff3d7f', '#ffd23f', '#3ddc97', '#4cc9f0', '#9b5de5', '#ff7b00']

const ASSETS = '/defouloir/'
const PED_H = 1.0 // hauteur du socle : la base du cou est posée dessus
const HEAD_H = 1.7
const G = -9.82
const ENV = 1
const OBJ = 2
const SHARD = 4
const MAX_DECALS = 260
const MAX_OBJECTS = 40

interface Live {
  kind: Weapon
  mesh: THREE.Object3D
  body: CANNON.Body
  prev: THREE.Vector3
  color: string
  done: boolean
  lastImpact: number
}
interface Particle { mesh: THREE.Mesh; v: THREE.Vector3; life: number }
interface Shard { mesh: THREE.Mesh; body: CANNON.Body; life: number }
interface Debris { holder: THREE.Object3D; body: CANNON.Body; life: number; meshes: THREE.Mesh[] }

export interface EngineOptions {
  reduced: boolean
  onReady: () => void
  onError: (message: string) => void
  onHit: (weapon: Weapon) => void
  onKnock?: (slot: Slot) => void
}

const v3 = (v: CANNON.Vec3) => new THREE.Vector3(v.x, v.y, v.z)
const rand = (a: number, b: number) => a + Math.random() * (b - a)
const pick = <T,>(xs: T[]) => xs[Math.floor(Math.random() * xs.length)]

export class Defouloir {
  weapon: Weapon | 'hasard' | 'postit' = 'peinture'
  paint = RAINBOW
  note = { text: 'Je fais ce que je veux', color: '#ffe066' }
  character: Character = 'homme'
  shape: Shape = { ...DEFAULT_SHAPE }
  readonly sounds = new Sounds()

  private renderer: THREE.WebGLRenderer
  private scene = new THREE.Scene()
  private camera: THREE.PerspectiveCamera
  private controls: OrbitControls
  private world = new CANNON.World({ gravity: new CANNON.Vec3(0, G, 0) })
  private clock = new THREE.Clock()
  private raycaster = new THREE.Raycaster()
  private pivot = new THREE.Group() // base du cou : la tête oscille autour
  private head: THREE.Mesh | null = null
  private costumeRoot = new THREE.Group() // repère des accessoires : identité pour le bonhomme, recalé sur la tête de la femme
  private subjectBody: CANNON.Body | null = null
  private pedestal: THREE.Mesh | null = null
  private pedestalBody: CANNON.Body | null = null
  private notes: THREE.Mesh[] = []
  private loading = 0
  private melonTexture: THREE.CanvasTexture | null = null
  private targets: THREE.Mesh[] = []
  private decals: THREE.Mesh[] = []
  private decalMaterials = new Map<string, THREE.MeshPhongMaterial>()
  private decalTextures: { map: THREE.Texture; normal: THREE.Texture }
  private live: Live[] = []
  private particles: Particle[] = []
  private shards: Shard[] = []
  private debris: Debris[] = []
  private worn: Partial<Record<Slot, { key: string; obj: THREE.Object3D; meshes: THREE.Mesh[] }>> = {}
  private costume: Costume | null = null
  private wobble = { x: 0, z: 0, vx: 0, vz: 0 }
  private shake = 0
  private observer: ResizeObserver
  private disposed = false
  private down: { x: number; y: number; t: number; moved: boolean; fired: boolean } | null = null
  private pointer = { x: 0, y: 0 }
  private holdTimer = 0
  private burstTimer = 0
  private binderTexture: THREE.CanvasTexture
  private dropGeometry = new THREE.SphereGeometry(0.018, 6, 4)
  private dropMaterials = new Map<string, THREE.MeshBasicMaterial>()
  private dropMaterial(color: string) {
    if (!this.dropMaterials.has(color)) this.dropMaterials.set(color, new THREE.MeshBasicMaterial({ color }))
    return this.dropMaterials.get(color)!
  }

  constructor(private container: HTMLElement, private opts: EngineOptions) {
    const { clientWidth: w, clientHeight: h } = container
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5))
    this.renderer.setSize(w, h)
    this.renderer.shadowMap.enabled = true
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap
    this.renderer.outputColorSpace = THREE.SRGBColorSpace
    this.renderer.domElement.style.touchAction = 'none'
    this.renderer.domElement.style.cursor = 'crosshair'
    container.appendChild(this.renderer.domElement)

    this.camera = new THREE.PerspectiveCamera(42, w / Math.max(h, 1), 0.05, 100)
    this.camera.position.set(0.45, 2.35, 3.9)
    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.target.set(0, PED_H + HEAD_H * 0.62, 0)
    this.controls.enablePan = false
    this.controls.minDistance = 1.6
    this.controls.maxDistance = 9
    this.controls.maxPolarAngle = Math.PI * 0.49
    this.controls.enableDamping = !opts.reduced
    this.controls.update()

    this.setupScene()
    const tex = new THREE.TextureLoader()
    this.decalTextures = { map: tex.load(`${ASSETS}decal-diffuse.png`), normal: tex.load(`${ASSETS}decal-normal.jpg`) }
    this.decalTextures.map.colorSpace = THREE.SRGBColorSpace
    this.binderTexture = binderLabel()
    this.pivot.add(this.costumeRoot)
    void this.loadHead()

    const el = this.renderer.domElement
    el.addEventListener('pointerdown', this.onDown)
    el.addEventListener('pointermove', this.onMove)
    window.addEventListener('pointerup', this.onUp)
    el.addEventListener('contextmenu', this.prevent)
    this.observer = new ResizeObserver(() => this.resize())
    this.observer.observe(container)
    this.renderer.setAnimationLoop(this.frame)
  }

  // ------------------------------------------------------------------ scène
  private setupScene() {
    const s = this.scene
    s.fog = new THREE.Fog(0xf3ecff, 12, 26)
    s.add(new THREE.HemisphereLight(0xffffff, 0x8a7fb0, 1.4))
    const sun = new THREE.DirectionalLight(0xffffff, 2.4)
    sun.position.set(3, 7, 5)
    sun.castShadow = true
    sun.shadow.mapSize.set(1024, 1024)
    Object.assign(sun.shadow.camera, { left: -4, right: 4, top: 4, bottom: -4, near: 1, far: 20 })
    sun.shadow.bias = -0.0005
    s.add(sun)
    const fill = new THREE.DirectionalLight(0xffd6e8, 0.6)
    fill.position.set(-4, 3, -2)
    s.add(fill)

    const floor = new THREE.Mesh(new THREE.CircleGeometry(9, 64), new THREE.MeshStandardMaterial({ color: 0xf4efe6, roughness: 0.95 }))
    floor.rotation.x = -Math.PI / 2
    floor.receiveShadow = true
    floor.name = 'sol'
    s.add(floor)
    const pedestal = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.52, PED_H, 40), new THREE.MeshStandardMaterial({ color: 0xffd23f, roughness: 0.6 }))
    pedestal.position.y = PED_H / 2
    pedestal.castShadow = pedestal.receiveShadow = true
    pedestal.name = 'socle'
    s.add(pedestal)
    this.pedestal = pedestal
    this.targets.push(floor, pedestal)
    this.pivot.position.set(0, PED_H, 0)
    s.add(this.pivot)

    const w = this.world
    w.broadphase = new CANNON.SAPBroadphase(w)
    w.allowSleep = true
    w.defaultContactMaterial.friction = 0.45
    w.defaultContactMaterial.restitution = 0.28
    const ground = new CANNON.Body({ mass: 0, shape: new CANNON.Plane(), collisionFilterGroup: ENV, collisionFilterMask: OBJ | SHARD })
    ground.quaternion.setFromEuler(-Math.PI / 2, 0, 0)
    w.addBody(ground)
    const base = new CANNON.Body({ mass: 0, collisionFilterGroup: ENV, collisionFilterMask: OBJ | SHARD })
    base.addShape(new CANNON.Cylinder(0.42, 0.52, PED_H, 16))
    base.position.set(0, PED_H / 2, 0)
    w.addBody(base)
    this.pedestalBody = base
  }

  private async loadHead() {
    const ticket = ++this.loading
    try {
      const tex = new THREE.TextureLoader()
      const [gltf, map, normal] = await Promise.all([
        new GLTFLoader().loadAsync(`${ASSETS}LeePerrySmith.glb`),
        tex.loadAsync(`${ASSETS}Map-COL.jpg`),
        tex.loadAsync(`${ASSETS}Infinite-Level_02_Tangent_SmoothUV.jpg`),
      ])
      if (this.disposed || ticket !== this.loading) return
      map.colorSpace = THREE.SRGBColorSpace
      const head = gltf.scene.children[0] as THREE.Mesh
      head.material = new THREE.MeshPhongMaterial({ map, normalMap: normal, specular: 0x222222, shininess: 22 })
      head.castShadow = true
      head.name = 'tete'
      // Mise à l'échelle : base du cou posée sur le socle, centrée, hauteur fixe
      head.position.set(0, 0, 0)
      this.pivot.add(head)
      this.pivot.updateMatrixWorld(true)
      let box = new THREE.Box3().setFromObject(head)
      head.scale.multiplyScalar(HEAD_H / box.getSize(new THREE.Vector3()).y)
      this.pivot.updateMatrixWorld(true)
      box = new THREE.Box3().setFromObject(head)
      const c = box.getCenter(new THREE.Vector3())
      head.position.set(-c.x, PED_H - box.min.y, -c.z)
      this.pivot.updateMatrixWorld(true)
      box = new THREE.Box3().setFromObject(head)
      this.head = head
      this.targets.unshift(head)

      // Collision approchée (les taches, elles, visent le vrai maillage)
      const size = box.getSize(new THREE.Vector3())
      const r = Math.min(size.x, size.z) * 0.48
      const body = new CANNON.Body({ mass: 0, collisionFilterGroup: ENV, collisionFilterMask: OBJ | SHARD })
      body.addShape(new CANNON.Sphere(r), new CANNON.Vec3(0, box.max.y - r - PED_H, 0))
      body.addShape(new CANNON.Sphere(r * 0.82), new CANNON.Vec3(0, size.y * 0.38, size.z * 0.08))
      body.addShape(new CANNON.Cylinder(r * 0.5, r * 0.55, size.y * 0.35, 12), new CANNON.Vec3(0, size.y * 0.17, 0))
      body.position.set(0, PED_H, 0)
      this.world.addBody(body)
      this.subjectBody = body
      this.costumeRoot.position.set(0, 0, 0)
      this.costumeRoot.scale.setScalar(1)
      if (this.costume) this.setCostume(this.costume, true)
      this.opts.onReady()
    } catch (error) {
      this.opts.onError(error instanceof Error ? error.message : String(error))
    }
  }

  // ------------------------------------------------------------------ interaction
  private prevent = (e: Event) => e.preventDefault()

  private onDown = (e: PointerEvent) => {
    if (e.button !== 0) return
    this.sounds.unlock()
    this.down = { x: e.clientX, y: e.clientY, t: performance.now(), moved: false, fired: false }
    this.pointer = { x: e.clientX, y: e.clientY }
    window.clearTimeout(this.holdTimer)
    this.holdTimer = window.setTimeout(() => {
      if (!this.down || this.down.moved || this.weapon === 'postit') return
      this.down.fired = true
      this.controls.enabled = false
      const fire = () => this.throwAt(this.pointer.x, this.pointer.y)
      fire()
      this.burstTimer = window.setInterval(fire, 110) // clic maintenu : rafale
    }, 320)
  }

  private onMove = (e: PointerEvent) => {
    this.pointer = { x: e.clientX, y: e.clientY }
    if (this.down && !this.down.fired && Math.hypot(e.clientX - this.down.x, e.clientY - this.down.y) > 6) this.down.moved = true
  }

  private onUp = () => {
    window.clearTimeout(this.holdTimer)
    window.clearInterval(this.burstTimer)
    this.controls.enabled = true
    if (this.down && !this.down.moved && !this.down.fired) this.throwAt(this.down.x, this.down.y)
    this.down = null
  }

  throwAt(clientX: number, clientY: number, weapon?: Weapon) {
    if (!weapon && this.weapon === 'postit') { this.stick(clientX, clientY); return }
    const rect = this.renderer.domElement.getBoundingClientRect()
    const ndc = new THREE.Vector2(((clientX - rect.left) / rect.width) * 2 - 1, -((clientY - rect.top) / rect.height) * 2 + 1)
    this.raycaster.setFromCamera(ndc, this.camera)
    this.raycaster.far = 60
    const hit = this.raycaster.intersectObjects(this.targets, false)[0]
    const target = hit ? hit.point : this.raycaster.ray.at(14, new THREE.Vector3())
    this.launch(weapon ?? (this.weapon === 'hasard' || this.weapon === 'postit' ? pick(WEAPONS) : this.weapon), target)
  }

  /** Lance un objet de la « main » (bas droite de la caméra) vers la cible, en cloche. */
  launch(kind: Weapon, target: THREE.Vector3) {
    const cam = this.camera
    const fwd = cam.getWorldDirection(new THREE.Vector3())
    const right = new THREE.Vector3().crossVectors(fwd, cam.up).normalize()
    const up = new THREE.Vector3().crossVectors(right, fwd).normalize()
    const start = cam.position.clone().addScaledVector(fwd, 0.7).addScaledVector(right, 0.35).addScaledVector(up, -0.3)
    const d = target.clone().sub(start)
    const t = THREE.MathUtils.clamp(d.length() / 10, 0.28, 0.8)
    const v = d.divideScalar(t).add(new THREE.Vector3(0, -0.5 * G * t, 0))

    const { mesh, shape, mass, color } = this.build(kind)
    const body = new CANNON.Body({ mass, shape, collisionFilterGroup: OBJ, collisionFilterMask: ENV | OBJ, linearDamping: 0.01, angularDamping: 0.1 })
    body.position.set(start.x, start.y, start.z)
    body.velocity.set(v.x, v.y, v.z)
    if (kind === 'tarte') {
      const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), v.clone().normalize().negate())
      body.quaternion.set(q.x, q.y, q.z, q.w) // la crème en avant
    } else {
      body.angularVelocity.set(rand(-8, 8), rand(-8, 8), rand(-8, 8))
    }
    body.allowSleep = true
    this.world.addBody(body)
    mesh.position.copy(start)
    this.scene.add(mesh)
    this.live.push({ kind, mesh, body, prev: start.clone(), color, done: false, lastImpact: 0 })
    this.sounds.whoosh()
    this.trim()
  }

  private build(kind: Weapon): { mesh: THREE.Object3D; shape: CANNON.Shape; mass: number; color: string } {
    const std = (color: THREE.ColorRepresentation, extra: THREE.MeshStandardMaterialParameters = {}) =>
      new THREE.MeshStandardMaterial({ color, roughness: 0.45, ...extra })
    const shadow = (o: THREE.Object3D) => { o.traverse((c) => { if ((c as THREE.Mesh).isMesh) c.castShadow = true }); return o }
    switch (kind) {
      case 'peinture': {
        const color = this.paint === RAINBOW ? pick(PALETTE) : this.paint
        const m = new THREE.Mesh(new THREE.SphereGeometry(0.11, 24, 16), std(color, { roughness: 0.2 }))
        return { mesh: shadow(m), shape: new CANNON.Sphere(0.11), mass: 0.3, color }
      }
      case 'tomate': {
        const g = new THREE.Group()
        g.add(new THREE.Mesh(new THREE.SphereGeometry(0.1, 24, 16), std(0xe63946, { roughness: 0.3 })))
        const leaf = new THREE.Mesh(new THREE.ConeGeometry(0.04, 0.03, 5), std(0x2d6a4f))
        leaf.position.y = 0.1
        g.add(leaf)
        return { mesh: shadow(g), shape: new CANNON.Sphere(0.1), mass: 0.2, color: '#c1121f' }
      }
      case 'oeuf': {
        const m = new THREE.Mesh(new THREE.SphereGeometry(0.065, 24, 16), std(0xfff3dc, { roughness: 0.5 }))
        m.scale.set(1, 1.3, 1)
        return { mesh: shadow(m), shape: new CANNON.Sphere(0.07), mass: 0.06, color: '#ffc300' }
      }
      case 'tarte': {
        const g = new THREE.Group()
        const crust = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.19, 0.06, 32), std(0xd9a066, { roughness: 0.8 }))
        const cream = new THREE.Mesh(new THREE.SphereGeometry(0.2, 32, 12, 0, Math.PI * 2, 0, Math.PI / 2), std(0xfffdf5, { roughness: 0.7 }))
        cream.scale.y = 0.35
        cream.position.y = 0.03
        g.add(crust, cream)
        return { mesh: shadow(g), shape: new CANNON.Cylinder(0.22, 0.19, 0.1, 12), mass: 0.4, color: '#fffdf5' }
      }
      case 'verre': {
        const pts = [[0, 0], [0.07, 0], [0.072, 0.008], [0.012, 0.016], [0.01, 0.13], [0.05, 0.16], [0.085, 0.22], [0.08, 0.31], [0.076, 0.31], [0.08, 0.22], [0.047, 0.165], [0, 0.155]]
          .map(([x, y]) => new THREE.Vector2(x, y))
        const geo = new THREE.LatheGeometry(pts, 32)
        geo.translate(0, -0.155, 0)
        const g = new THREE.Group()
        g.add(new THREE.Mesh(geo, new THREE.MeshPhysicalMaterial({ color: 0xdff6ff, roughness: 0.05, metalness: 0, transparent: true, opacity: 0.45, side: THREE.DoubleSide })))
        const wine = new THREE.Mesh(new THREE.CylinderGeometry(0.068, 0.045, 0.06, 24), std(0x7b0828, { roughness: 0.1 }))
        wine.position.y = 0.03
        g.add(wine)
        return { mesh: shadow(g), shape: new CANNON.Cylinder(0.08, 0.07, 0.31, 10), mass: 0.25, color: '#6a040f' }
      }
      case 'tasse': {
        const g = new THREE.Group()
        g.add(new THREE.Mesh(new THREE.CylinderGeometry(0.085, 0.075, 0.15, 28), std(0xffffff, { roughness: 0.25 })))
        const handle = new THREE.Mesh(new THREE.TorusGeometry(0.045, 0.014, 10, 20), std(0xffffff, { roughness: 0.25 }))
        handle.position.x = 0.1
        const coffee = new THREE.Mesh(new THREE.CircleGeometry(0.075, 24), std(0x3b2316))
        coffee.rotation.x = -Math.PI / 2
        coffee.position.y = 0.06
        g.add(handle, coffee)
        return { mesh: shadow(g), shape: new CANNON.Cylinder(0.085, 0.075, 0.15, 10), mass: 0.35, color: '#4b2e1e' }
      }
      case 'melon': {
        this.melonTexture ??= melonStripes()
        const m = new THREE.Mesh(new THREE.SphereGeometry(0.17, 32, 20), new THREE.MeshStandardMaterial({ map: this.melonTexture, roughness: 0.5 }))
        m.scale.set(1, 0.9, 1.15)
        return { mesh: shadow(m), shape: new CANNON.Sphere(0.17), mass: 1.8, color: '#e63946' }
      }
      case 'classeur': {
        const color = pick(['#4cc9f0', '#9b5de5', '#ff3d7f', '#3ddc97'])
        const side = std(color)
        const face = new THREE.MeshStandardMaterial({ map: this.binderTexture, color, roughness: 0.6 })
        const m = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.42, 0.07), [side, side, side, side, face, face])
        return { mesh: shadow(m), shape: new CANNON.Box(new CANNON.Vec3(0.16, 0.21, 0.035)), mass: 1.2, color }
      }
    }
  }

  // ------------------------------------------------------------------ impacts
  private impact(o: Live, hit: THREE.Intersection, velocity: THREE.Vector3) {
    const speed = velocity.length()
    const normal = hit.face ? hit.face.normal.clone().transformDirection(hit.object.matrixWorld) : velocity.clone().normalize().negate()
    const slot = this.slotOf(hit.object)
    const worn = slot !== null && this.worn[slot]?.meshes.includes(hit.object as THREE.Mesh)
    const onHead = hit.object === this.head || !!worn
    if (worn && slot && (slot === 'chapeau' || slot === 'lunettes' || slot === 'nez') && speed > (o.kind === 'classeur' ? 2.5 : 5.5)) {
      queueMicrotask(() => this.knock(slot, velocity))
    }
    const splat = (size: number, color: string, spread = 4) => {
      this.decal(hit.object as THREE.Mesh, hit.point, normal, size, color)
      for (let i = 0; i < spread; i++) this.droplet(hit.point, normal, size, color)
      this.sprinkle(hit.point, normal, velocity, color, this.opts.reduced ? 0 : 14)
    }
    switch (o.kind) {
      case 'peinture': splat(rand(0.45, 0.7), o.color, 5); this.sounds.splat(); break
      case 'tomate': splat(rand(0.35, 0.5), o.color, 4); this.sounds.splat(0.8); break
      case 'melon':
        splat(rand(0.8, 1.0), o.color, 7)
        this.shatter(hit.point, velocity, 0x2d6a4f, this.opts.reduced ? 5 : 12, 0.09)
        this.sprinkle(hit.point, velocity.clone().normalize().negate(), velocity, '#1b1530', this.opts.reduced ? 0 : 10)
        this.sounds.splat(1.5)
        break
      case 'oeuf':
        this.decal(hit.object as THREE.Mesh, hit.point, normal, 0.42, '#fff6dc')
        splat(0.22, o.color, 2)
        this.shatter(hit.point, velocity, 0xfff3dc, 6, 0.03)
        this.sounds.crack()
        break
      case 'tarte': splat(rand(0.7, 0.9), o.color, 6); this.sounds.splat(1.2); break
      case 'verre':
        if (speed < 3) return false
        splat(0.38, o.color, 3)
        this.shatter(hit.point, velocity, 0xdff6ff, this.opts.reduced ? 8 : 22, 0.05, true)
        this.sounds.glass()
        break
      case 'tasse':
        if (speed < 3) return false
        splat(0.4, o.color, 3)
        this.shatter(hit.point, velocity, 0xffffff, this.opts.reduced ? 6 : 14, 0.06)
        this.sounds.ceramic()
        break
      case 'classeur': {
        const t = performance.now()
        if (speed < 1.5 || t - o.lastImpact < 250) return false
        o.lastImpact = t
        this.sounds.thud(Math.min(speed / 10, 1))
        if (onHead) this.hitHead(velocity, o.kind)
        return false
      } // il rebondit, la physique s'en charge
    }
    if (onHead) this.hitHead(velocity, o.kind)
    return true
  }

  private hitHead(velocity: THREE.Vector3, kind: Weapon) {
    if (!this.opts.reduced) {
      const k = Math.min(velocity.length(), 14) * 0.035
      const dir = velocity.clone().normalize()
      this.wobble.vx += dir.z * k * 6
      this.wobble.vz -= dir.x * k * 6
      this.shake = Math.min(this.shake + 0.04, 0.08)
    }
    this.opts.onHit(kind)
  }

  private decalMaterial(color: string) {
    let m = this.decalMaterials.get(color)
    if (!m) {
      m = new THREE.MeshPhongMaterial({
        color, specular: 0x444444, shininess: 30, map: this.decalTextures.map, normalMap: this.decalTextures.normal,
        transparent: true, depthTest: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -4,
      })
      m.userData.shared = true
      this.decalMaterials.set(color, m)
    }
    return m
  }

  /** Tache projetée sur le maillage cible, puis rattachée à lui (elle suit la tête quand elle bouge). */
  private decal(target: THREE.Mesh, point: THREE.Vector3, normal: THREE.Vector3, size: number, color: string) {
    if (this.character === 'femme') size *= 0.5  // personnage en pied : taches à l'échelle du corps
    const helper = new THREE.Object3D()
    helper.position.copy(point)
    helper.lookAt(point.clone().add(normal))
    const orientation = helper.rotation.clone()
    orientation.z = Math.random() * Math.PI * 2
    target.updateMatrixWorld(true)
    const geometry = new DecalGeometry(target, point, orientation, new THREE.Vector3(size, size, size))
    if (!geometry.getAttribute('position')?.count) { geometry.dispose(); return }
    geometry.applyMatrix4(target.matrixWorld.clone().invert())
    const mesh = new THREE.Mesh(geometry, this.decalMaterial(color))
    mesh.renderOrder = this.decals.length + 1
    target.add(mesh)
    this.decals.push(mesh)
    while (this.decals.length > MAX_DECALS) {
      const old = this.decals.shift()!
      old.removeFromParent()
      old.geometry.dispose()
    }
  }

  /** Éclaboussures secondaires : petites taches autour du point d'impact. */
  private droplet(point: THREE.Vector3, normal: THREE.Vector3, size: number, color: string) {
    const tangent = new THREE.Vector3(rand(-1, 1), rand(-1, 1), rand(-1, 1)).cross(normal).normalize()
    const origin = point.clone().addScaledVector(tangent, rand(size * 0.4, size * 1.1)).addScaledVector(normal, 0.4)
    this.raycaster.set(origin, normal.clone().negate())
    this.raycaster.far = 0.9
    const hit = this.raycaster.intersectObjects(this.targets, false)[0]
    if (!hit) return
    const n = hit.face ? hit.face.normal.clone().transformDirection(hit.object.matrixWorld) : normal
    this.decal(hit.object as THREE.Mesh, hit.point, n, rand(0.06, size * 0.3), color)
  }

  private sprinkle(point: THREE.Vector3, normal: THREE.Vector3, velocity: THREE.Vector3, color: string, count: number) {
    const geo = this.dropGeometry
    const mat = this.dropMaterial(color)
    for (let i = 0; i < count; i++) {
      const m = new THREE.Mesh(geo, mat)
      m.position.copy(point).addScaledVector(normal, 0.03)
      const v = normal.clone().multiplyScalar(rand(1, 3)).add(new THREE.Vector3(rand(-2, 2), rand(0, 2.5), rand(-2, 2))).addScaledVector(velocity, 0.08)
      this.scene.add(m)
      this.particles.push({ mesh: m, v, life: rand(0.5, 0.9) })
    }
  }

  private shatter(point: THREE.Vector3, velocity: THREE.Vector3, color: number, count: number, size: number, glass = false) {
    const mat = glass
      ? new THREE.MeshPhysicalMaterial({ color, roughness: 0.05, transparent: true, opacity: 0.6, side: THREE.DoubleSide })
      : new THREE.MeshStandardMaterial({ color, roughness: 0.3, side: THREE.DoubleSide })
    for (let i = 0; i < count; i++) {
      const s = rand(size * 0.4, size)
      const mesh = new THREE.Mesh(new THREE.TetrahedronGeometry(s, 0), mat)
      mesh.scale.set(1, rand(0.15, 0.4), rand(0.6, 1.2))
      mesh.castShadow = true
      const body = new CANNON.Body({ mass: 0.01, shape: new CANNON.Sphere(s * 0.35), collisionFilterGroup: SHARD, collisionFilterMask: ENV })
      body.position.set(point.x + rand(-0.04, 0.04), point.y + rand(0, 0.05), point.z + rand(-0.04, 0.04))
      const out = velocity.clone().multiplyScalar(-0.15).add(new THREE.Vector3(rand(-3, 3), rand(0.5, 3.5), rand(-3, 3)))
      body.velocity.set(out.x, out.y, out.z)
      body.angularVelocity.set(rand(-20, 20), rand(-20, 20), rand(-20, 20))
      body.linearDamping = 0.05
      this.world.addBody(body)
      this.scene.add(mesh)
      this.shards.push({ mesh, body, life: rand(7, 11) })
    }
    while (this.shards.length > 320) this.removeShard(this.shards.shift()!)
  }

  private removeShard(s: Shard) {
    this.world.removeBody(s.body)
    s.mesh.removeFromParent()
    s.mesh.geometry.dispose()
  }

  private removeDebris(d: Debris) {
    this.world.removeBody(d.body)
    this.targets = this.targets.filter((t) => !d.meshes.includes(t))
    d.holder.removeFromParent()
    disposeTree(d.holder)
  }

  private removeLive(o: Live) {
    o.done = true
    this.world.removeBody(o.body)
    o.mesh.removeFromParent()
    o.mesh.traverse((c) => { if ((c as THREE.Mesh).isMesh) (c as THREE.Mesh).geometry.dispose() })
  }

  private trim() {
    const resting = this.live.filter((o) => !o.done)
    for (const o of resting.slice(0, Math.max(0, resting.length - MAX_OBJECTS))) this.removeLive(o)
    this.live = this.live.filter((o) => !o.done)
  }

  // ------------------------------------------------------------------ personnage
  /** Change de personnage : la tête sur socle (« homme ») ou une femme en pied (« femme »), réglable (taille, corpulence, tête). */
  setCharacter(kind: Character, shape: Shape = this.shape) {
    this.character = kind
    this.shape = { ...shape }
    this.removeSubject()
    const femme = kind === 'femme'
    if (this.pedestal) this.pedestal.visible = !femme
    if (this.pedestalBody) {
      if (femme) this.world.removeBody(this.pedestalBody)
      else if (!this.world.bodies.includes(this.pedestalBody)) this.world.addBody(this.pedestalBody)
    }
    this.targets = this.targets.filter((t) => t !== this.pedestal)
    if (!femme && this.pedestal) this.targets.push(this.pedestal)
    this.pivot.position.set(0, femme ? 0 : PED_H, 0)
    this.controls.target.set(0, femme ? 1.1 : PED_H + HEAD_H * 0.62, 0)
    this.camera.position.set(0.35, femme ? 1.45 : 2.35, femme ? 3.3 : 3.9)
    this.controls.update()
    if (femme) void this.loadWoman()
    else void this.loadHead()
  }

  /** Taille, corpulence, tête (femme) : le personnage est recuit dans sa nouvelle silhouette. */
  setShape(shape: Shape) {
    this.shape = { ...shape }
    if (this.character === 'femme') { this.removeSubject(); void this.loadWoman() }
  }

  private removeSubject() {
    for (const n of this.notes) { n.removeFromParent(); n.geometry.dispose() }
    this.notes = []
    if (this.head) {
      this.decals = this.decals.filter((d) => d.parent !== this.head)
      this.targets = this.targets.filter((t) => t !== this.head)
      this.head.removeFromParent()
      disposeTree(this.head)
      this.head = null
    }
    if (this.subjectBody) { this.world.removeBody(this.subjectBody); this.subjectBody = null }
  }

  private async loadWoman() {
    const ticket = ++this.loading
    try {
      const gltf = await new GLTFLoader().loadAsync(`${ASSETS}Michelle.glb`)
      if (this.disposed || ticket !== this.loading) return
      const scene = gltf.scene
      let skinned: THREE.SkinnedMesh | null = null
      scene.traverse((o) => { if ((o as THREE.SkinnedMesh).isSkinnedMesh && !skinned) skinned = o as THREE.SkinnedMesh })
      if (!skinned) throw new Error('personnage introuvable dans le fichier')
      const sk = skinned as THREE.SkinnedMesh
      // Pose figée (début de l'animation, debout), tête réglable, puis « cuisson » en maillage statique :
      // taches, accessoires et post-its se posent alors exactement sur la silhouette affichée.
      const clip = gltf.animations.find((a) => a.name === 'SambaDance') ?? gltf.animations[0]
      if (clip) {
        const mixer = new THREE.AnimationMixer(scene)
        mixer.clipAction(clip).play()
        mixer.setTime(0.05)
      }
      const headBone = sk.skeleton.bones.find((b) => b.name.endsWith('Head'))
      const topBone = sk.skeleton.bones.find((b) => b.name.endsWith('HeadTop_End'))
      if (headBone) headBone.scale.setScalar(this.shape.head)
      scene.updateMatrixWorld(true)
      sk.skeleton.update()
      const src = sk.geometry
      const count = src.attributes.position.count
      const positions = new Float32Array(count * 3)
      const v = new THREE.Vector3()
      for (let i = 0; i < count; i++) {
        sk.getVertexPosition(i, v)
        v.applyMatrix4(sk.matrixWorld)
        positions.set([v.x, v.y, v.z], i * 3)
      }
      const geo = new THREE.BufferGeometry()
      geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
      if (src.attributes.uv) geo.setAttribute('uv', src.attributes.uv.clone())
      if (src.index) geo.setIndex(src.index.clone())
      geo.computeVertexNormals()
      // Mise à l'échelle : pieds au sol, centrée, taille et corpulence réglables
      geo.computeBoundingBox()
      const box0 = geo.boundingBox!
      const k = (FEMME_H * this.shape.height) / (box0.max.y - box0.min.y)
      const c0 = box0.getCenter(new THREE.Vector3())
      const sx = k * this.shape.build
      const matrix = new THREE.Matrix4().makeScale(sx, k, sx).multiply(new THREE.Matrix4().makeTranslation(-c0.x, -box0.min.y, -c0.z))
      geo.applyMatrix4(matrix)
      geo.computeBoundingBox()
      geo.computeBoundingSphere()
      const material = (Array.isArray(sk.material) ? sk.material[0] : sk.material) as THREE.MeshStandardMaterial
      const mesh = new THREE.Mesh(geo, material)
      mesh.castShadow = true
      mesh.name = 'personnage'
      this.pivot.add(mesh)
      this.head = mesh
      this.targets.unshift(mesh)
      // Repère des accessoires : la tête du bonhomme → la tête de la femme
      const toLocal = (b?: THREE.Bone) => (b ? b.getWorldPosition(new THREE.Vector3()).applyMatrix4(matrix) : null)
      const neck = toLocal(headBone)
      const top = toLocal(topBone)
      if (neck && top) {
        const chin = neck.y - (top.y - neck.y) * 0.25
        const headH = top.y - chin
        const center = new THREE.Vector3(neck.x, (top.y + chin) / 2, neck.z + headH * 0.06)
        const scale = headH / LEE_HEAD_HEIGHT
        this.costumeRoot.scale.setScalar(scale)
        this.costumeRoot.position.copy(center).sub(LEE_HEAD_CENTER.clone().multiplyScalar(scale))
      }
      // Collision approchée : corps + tête
      const size = geo.boundingBox!.getSize(new THREE.Vector3())
      const body = new CANNON.Body({ mass: 0, collisionFilterGroup: ENV, collisionFilterMask: OBJ | SHARD })
      // centre réel du torse (le maillage n'est pas centré en z : la pose déporte bras et hanches)
      const p = geo.attributes.position
      const torso = new THREE.Vector3()
      let n = 0
      for (let i = 0; i < p.count; i++) {
        const y = p.getY(i)
        if (y > size.y * 0.5 && y < size.y * 0.75 && Math.abs(p.getX(i)) < 0.15 * this.shape.build) { torso.x += p.getX(i); torso.z += p.getZ(i); n++ }
      }
      if (n) torso.divideScalar(n)
      const headPos = neck ?? new THREE.Vector3(0, size.y * 0.9, 0)
      body.addShape(new CANNON.Cylinder(0.11 * this.shape.build, 0.13 * this.shape.build, size.y * 0.8, 12), new CANNON.Vec3(torso.x, size.y * 0.4, torso.z))
      body.addShape(new CANNON.Sphere(0.1 * this.shape.head * this.shape.height), new CANNON.Vec3(headPos.x, headPos.y + 0.08 * this.shape.height, headPos.z))
      this.world.addBody(body)
      this.subjectBody = body
      if (this.costume) this.setCostume(this.costume, true)
      this.opts.onReady()
    } catch (error) {
      this.opts.onError(error instanceof Error ? error.message : String(error))
    }
  }

  // ------------------------------------------------------------------ post-its
  /** Colle un post-it (texte et couleur choisis) là où l'on clique sur le personnage ; il suit ses mouvements. */
  private stick(clientX: number, clientY: number) {
    const rect = this.renderer.domElement.getBoundingClientRect()
    const ndc = new THREE.Vector2(((clientX - rect.left) / rect.width) * 2 - 1, -((clientY - rect.top) / rect.height) * 2 + 1)
    this.raycaster.setFromCamera(ndc, this.camera)
    this.raycaster.far = 60
    const hit = this.raycaster.intersectObjects(this.targets, false)[0]
    if (!hit || !hit.face) return
    const normal = hit.face.normal.clone().transformDirection(hit.object.matrixWorld)
    const size = this.character === 'femme' ? 0.16 : 0.24
    const note = new THREE.Mesh(new THREE.PlaneGeometry(size, size), new THREE.MeshStandardMaterial({
      map: noteTexture(this.note.text, this.note.color), roughness: 0.9, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2,
    }))
    note.position.copy(hit.point).addScaledVector(normal, 0.012)
    note.lookAt(hit.point.clone().add(normal))
    note.rotateZ(rand(-0.3, 0.3))
    note.castShadow = true
    hit.object.attach(note)
    this.notes.push(note)
    this.sounds.thud(0.15)
  }

  /** Pose le déguisement : seuls les emplacements modifiés sont reconstruits. */
  setCostume(costume: Costume, force = false) {
    this.costume = costume
    if (!this.head) return
    for (const slot of SLOTS) {
      const style = costume[slot]
      const key = style.item ? `${style.item}|${style.color}|${style.size}` : ''
      const current = this.worn[slot]
      if (!force && (current?.key ?? '') === key) continue
      if (current) this.takeOff(slot)
      const obj = accessory(slot, style)
      if (!obj) continue
      const meshes: THREE.Mesh[] = []
      obj.traverse((o) => { if ((o as THREE.Mesh).isMesh) meshes.push(o as THREE.Mesh) })
      this.costumeRoot.add(obj)
      this.targets.push(...meshes)
      this.worn[slot] = { key, obj, meshes }
    }
  }

  private takeOff(slot: Slot) {
    const w = this.worn[slot]
    if (!w) return
    this.targets = this.targets.filter((t) => !w.meshes.includes(t))
    this.decals = this.decals.filter((d) => !w.meshes.includes(d.parent as THREE.Mesh))
    w.obj.removeFromParent()
    disposeTree(w.obj)
    delete this.worn[slot]
  }

  private slotOf(o: THREE.Object3D): Slot | null {
    return (o.userData.slot as Slot | undefined) ?? null
  }

  /** Un chapeau ou des lunettes bien visés s'envolent (physique), jusqu'à « Remettre le déguisement ». */
  private knock(slot: Slot, velocity: THREE.Vector3) {
    const w = this.worn[slot]
    if (!w) return
    delete this.worn[slot]
    const box = new THREE.Box3().setFromObject(w.obj)
    const center = box.getCenter(new THREE.Vector3())
    const half = box.getSize(new THREE.Vector3()).multiplyScalar(0.5).max(new THREE.Vector3(0.03, 0.03, 0.03))
    const holder = new THREE.Object3D()
    holder.position.copy(center)
    this.scene.add(holder)
    holder.attach(w.obj)
    const body = new CANNON.Body({ mass: 0.3, shape: new CANNON.Box(new CANNON.Vec3(half.x, half.y, half.z)), collisionFilterGroup: OBJ, collisionFilterMask: ENV | OBJ })
    body.position.set(center.x, center.y, center.z)
    const v = velocity.clone().multiplyScalar(0.45).add(new THREE.Vector3(0, 2.5, 0))
    body.velocity.set(v.x, v.y, v.z)
    body.angularVelocity.set(rand(-6, 6), rand(-6, 6), rand(-6, 6))
    this.world.addBody(body)
    this.debris.push({ holder, body, life: 14, meshes: w.meshes })
    this.opts.onKnock?.(slot)
  }

  clean() {
    for (const n of this.notes) { n.removeFromParent(); n.geometry.dispose() }
    this.notes = []
    for (const d of this.decals) { d.removeFromParent(); d.geometry.dispose() }
    this.decals = []
    for (const o of this.live) this.removeLive(o)
    this.live = []
    for (const s of this.shards) this.removeShard(s)
    this.shards = []
    for (const d of this.debris) this.removeDebris(d)
    this.debris = []
    if (this.costume) this.setCostume(this.costume)
    this.sounds.whoosh()
  }

  // ------------------------------------------------------------------ boucle
  private frame = () => {
    const dt = Math.min(this.clock.getDelta(), 1 / 30)
    this.world.step(1 / 60, dt, 3)

    const now = new THREE.Vector3()
    for (const o of this.live) {
      if (o.done) continue
      now.set(o.body.position.x, o.body.position.y, o.body.position.z)
      const seg = now.clone().sub(o.prev)
      const len = seg.length()
      if (len > (o.kind === 'classeur' ? 0.02 : 1e-4)) {
        this.raycaster.set(o.prev, seg.clone().normalize())
        this.raycaster.far = len + (o.kind === 'melon' ? 0.26 : 0.12)  // gros projectile : l'impact compte dès le contact
        const hit = this.raycaster.intersectObjects(this.targets, false)[0]
        if (hit && this.impact(o, hit, v3(o.body.velocity))) { this.removeLive(o); continue }
      }
      o.prev.copy(now)
      o.mesh.position.copy(now)
      o.mesh.quaternion.set(o.body.quaternion.x, o.body.quaternion.y, o.body.quaternion.z, o.body.quaternion.w)
      if (now.y < -5 || now.length() > 40) this.removeLive(o)
    }
    this.live = this.live.filter((o) => !o.done)

    for (const p of this.particles) {
      p.life -= dt
      p.v.y += G * dt
      p.mesh.position.addScaledVector(p.v, dt)
      if (p.mesh.position.y < 0.01) { p.mesh.position.y = 0.01; p.v.set(0, 0, 0) }
      p.mesh.scale.setScalar(Math.max(p.life / 0.9, 0.01))
      if (p.life <= 0) p.mesh.removeFromParent()
    }
    this.particles = this.particles.filter((p) => p.life > 0)

    for (const s of this.shards) {
      s.life -= dt
      s.mesh.position.set(s.body.position.x, s.body.position.y, s.body.position.z)
      s.mesh.quaternion.set(s.body.quaternion.x, s.body.quaternion.y, s.body.quaternion.z, s.body.quaternion.w)
      if (s.life <= 0) this.removeShard(s)
    }
    this.shards = this.shards.filter((s) => s.life > 0)

    for (const d of this.debris) {
      d.life -= dt
      d.holder.position.set(d.body.position.x, d.body.position.y, d.body.position.z)
      d.holder.quaternion.set(d.body.quaternion.x, d.body.quaternion.y, d.body.quaternion.z, d.body.quaternion.w)
      if (d.life <= 0 || d.body.position.y < -5) this.removeDebris(d)
    }
    this.debris = this.debris.filter((d) => d.life > 0 && d.body.position.y >= -5)

    // La tête encaisse : ressort amorti autour de la base du cou
    const w = this.wobble
    w.vx += (-60 * w.x - 7 * w.vx) * dt
    w.vz += (-60 * w.z - 7 * w.vz) * dt
    w.x += w.vx * dt
    w.z += w.vz * dt
    this.pivot.rotation.set(THREE.MathUtils.clamp(w.x, -0.35, 0.35), 0, THREE.MathUtils.clamp(w.z, -0.35, 0.35))

    this.controls.update()
    const offset = this.shake > 0.001 ? new THREE.Vector3(rand(-1, 1), rand(-1, 1), 0).multiplyScalar(this.shake) : null
    if (offset) this.camera.position.add(offset)
    this.renderer.render(this.scene, this.camera)
    if (offset) this.camera.position.sub(offset)
    this.shake *= 0.85
  }

  private resize() {
    const { clientWidth: w, clientHeight: h } = this.container
    if (!w || !h) return
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
    this.renderer.setSize(w, h)
  }

  dispose() {
    this.disposed = true
    this.renderer.setAnimationLoop(null)
    this.observer.disconnect()
    const el = this.renderer.domElement
    el.removeEventListener('pointerdown', this.onDown)
    el.removeEventListener('pointermove', this.onMove)
    window.removeEventListener('pointerup', this.onUp)
    el.removeEventListener('contextmenu', this.prevent)
    window.clearTimeout(this.holdTimer)
    window.clearInterval(this.burstTimer)
    this.controls.dispose()
    this.scene.traverse((o) => {
      const m = o as THREE.Mesh
      if (m.isMesh) {
        m.geometry.dispose()
        for (const mat of Array.isArray(m.material) ? m.material : [m.material]) mat.dispose()
      }
    })
    for (const m of this.decalMaterials.values()) m.dispose()
    for (const m of this.dropMaterials.values()) m.dispose()
    this.dropGeometry.dispose()
    this.decalTextures.map.dispose()
    this.decalTextures.normal.dispose()
    this.binderTexture.dispose()
    this.sounds.dispose()
    this.renderer.dispose()
    el.remove()
  }
}

function disposeTree(o: THREE.Object3D) {
  o.traverse((c) => {
    const m = c as THREE.Mesh
    if (!m.isMesh) return
    m.geometry.dispose()
    for (const mat of Array.isArray(m.material) ? m.material : [m.material]) {
      if (mat.userData?.shared) continue
      ;(mat as THREE.MeshStandardMaterial).map?.dispose()
      mat.dispose()
    }
  })
}

/** Étiquette « RFI » des classeurs, dessinée à la volée (aucun fichier). */
function binderLabel() {
  const c = document.createElement('canvas')
  c.width = 256
  c.height = 336
  const g = c.getContext('2d')!
  g.fillStyle = '#ffffff'
  g.fillRect(0, 0, 256, 336)
  g.fillStyle = '#1b1530'
  g.fillRect(40, 70, 176, 120)
  g.fillStyle = '#ffffff'
  g.font = 'bold 72px sans-serif'
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  g.fillText('RFI', 128, 132)
  g.fillStyle = '#1b1530'
  g.font = 'bold 26px sans-serif'
  g.fillText('v47 FINAL', 128, 240)
  g.fillText('(vraiment)', 128, 275)
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  return t
}

/** Écorce de melon : bandes vertes, dessinées à la volée. */
function melonStripes() {
  const c = document.createElement('canvas')
  c.width = 256
  c.height = 128
  const g = c.getContext('2d')!
  g.fillStyle = '#5a9e3a'
  g.fillRect(0, 0, 256, 128)
  g.fillStyle = '#2d6a4f'
  for (let x = 0; x < 256; x += 32) g.fillRect(x, 0, 14, 128)
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  return t
}

/** Post-it : carré de couleur, texte manuscrit retourné à la ligne. */
function noteTexture(text: string, color: string) {
  const c = document.createElement('canvas')
  c.width = 256
  c.height = 256
  const g = c.getContext('2d')!
  g.fillStyle = color
  g.fillRect(0, 0, 256, 256)
  g.fillStyle = 'rgba(0,0,0,0.08)'
  g.fillRect(0, 0, 256, 34)
  g.fillStyle = '#1b1530'
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  const words = (text || ' ').split(/\s+/)
  let size = 44
  let lines: string[] = []
  for (; size >= 18; size -= 2) {
    g.font = `bold ${size}px "Comic Sans MS", "Segoe Print", cursive`
    lines = []
    let line = ''
    for (const w of words) {
      const next = line ? `${line} ${w}` : w
      if (g.measureText(next).width > 220 && line) { lines.push(line); line = w } else line = next
    }
    lines.push(line)
    if (lines.length * size * 1.15 <= 200) break
  }
  lines.forEach((l, i) => g.fillText(l, 128, 140 + (i - (lines.length - 1) / 2) * size * 1.15))
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  return t
}
