/**
 * Champ d'étoiles en canvas 2D (léger) : parallaxe douce à la souris, scintillement, étoiles filantes rares.
 * En mouvement réduit : dessin statique unique. En arrière-plan d'onglet : pause.
 */
import { useEffect, useRef } from 'react'
import { useReducedMotion } from '../../motion/useReducedMotion'

interface Star { x: number; y: number; z: number; r: number; tw: number; hue: number }

export function Starfield() {
  const canvas = useRef<HTMLCanvasElement>(null)
  const reduced = useReducedMotion()

  useEffect(() => {
    const el = canvas.current
    if (!el) return
    const ctx = el.getContext('2d')
    if (!ctx) return
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5)
    let width = 0
    let height = 0
    let stars: Star[] = []
    let raf = 0
    const mouse = { x: 0, y: 0, tx: 0, ty: 0 }
    const shooting: { x: number; y: number; vx: number; vy: number; life: number }[] = []
    let shower = 0

    const resize = () => {
      width = window.innerWidth
      height = window.innerHeight
      el.width = width * dpr
      el.height = height * dpr
      el.style.width = `${width}px`
      el.style.height = `${height}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      const count = Math.round(Math.min(220, (width * height) / 9000))
      stars = Array.from({ length: count }, () => ({
        x: Math.random() * width, y: Math.random() * height, z: Math.random() * 0.9 + 0.1,
        r: Math.random() * 1.2 + 0.2, tw: Math.random() * Math.PI * 2, hue: Math.random(),
      }))
      if (reduced) draw(0)
    }

    const color = (hue: number, alpha: number) =>
      hue < 0.6 ? `rgba(244,239,255,${alpha})` : hue < 0.82 ? `rgba(196,181,253,${alpha})` : hue < 0.94 ? `rgba(245,223,165,${alpha})` : `rgba(94,234,212,${alpha})`

    const draw = (t: number) => {
      ctx.clearRect(0, 0, width, height)
      mouse.x += (mouse.tx - mouse.x) * 0.04
      mouse.y += (mouse.ty - mouse.y) * 0.04
      for (const s of stars) {
        const px = reduced ? 0 : mouse.x * s.z * 18
        const py = reduced ? 0 : mouse.y * s.z * 18
        const twinkle = reduced ? 0.8 : 0.55 + Math.sin(t * 0.0012 * (0.5 + s.z) + s.tw) * 0.45
        const x = (s.x + px + width) % width
        const y = (s.y + py + height) % height
        ctx.beginPath()
        ctx.fillStyle = color(s.hue, twinkle * (0.35 + s.z * 0.65))
        ctx.arc(x, y, s.r * (0.6 + s.z), 0, Math.PI * 2)
        ctx.fill()
      }
      if (!reduced) {
        if ((Math.random() < 0.0015 || shower > 0) && shooting.length < (shower > 0 ? 24 : 2)) {
          shooting.push({ x: Math.random() * width, y: Math.random() * height * 0.4, vx: 6 + Math.random() * 4, vy: 2 + Math.random() * 2, life: 1 })
        }
        shower = Math.max(0, shower - 1)
        for (let i = shooting.length - 1; i >= 0; i--) {
          const s = shooting[i]
          const grad = ctx.createLinearGradient(s.x, s.y, s.x - s.vx * 12, s.y - s.vy * 12)
          grad.addColorStop(0, `rgba(245,223,165,${s.life})`)
          grad.addColorStop(1, 'rgba(245,223,165,0)')
          ctx.strokeStyle = grad
          ctx.lineWidth = 1.4
          ctx.beginPath()
          ctx.moveTo(s.x, s.y)
          ctx.lineTo(s.x - s.vx * 12, s.y - s.vy * 12)
          ctx.stroke()
          s.x += s.vx
          s.y += s.vy
          s.life -= 0.012
          if (s.life <= 0) shooting.splice(i, 1)
        }
      }
    }

    const loop = (t: number) => {
      draw(t)
      raf = requestAnimationFrame(loop)
    }
    const onMove = (e: PointerEvent) => {
      mouse.tx = e.clientX / window.innerWidth - 0.5
      mouse.ty = e.clientY / window.innerHeight - 0.5
    }
    const onVisibility = () => {
      cancelAnimationFrame(raf)
      if (!document.hidden && !reduced) raf = requestAnimationFrame(loop)
    }
    const onShower = () => {
      shower = 180
    }

    resize()
    window.addEventListener('resize', resize)
    window.addEventListener('pointermove', onMove, { passive: true })
    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('merlin:shower', onShower)
    if (!reduced) raf = requestAnimationFrame(loop)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
      window.removeEventListener('pointermove', onMove)
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('merlin:shower', onShower)
    }
  }, [reduced])

  return <canvas ref={canvas} aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10" />
}
