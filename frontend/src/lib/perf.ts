/** Détection des capacités : la 3D n'est servie qu'aux machines qui peuvent la digérer. */
import { getLowPowerPref } from './storage'

let webglCache: boolean | null = null

export function hasWebGL(): boolean {
  if (webglCache !== null) return webglCache
  try {
    const canvas = document.createElement('canvas')
    const gl = canvas.getContext('webgl2') ?? canvas.getContext('webgl')
    webglCache = !!gl
    ;(gl as WebGLRenderingContext | null)?.getExtension('WEBGL_lose_context')?.loseContext()
  } catch {
    webglCache = false
  }
  return webglCache
}

export function isLowPowerDevice(): boolean {
  const nav = navigator as Navigator & { deviceMemory?: number; connection?: { saveData?: boolean } }
  if (nav.connection?.saveData) return true
  if (nav.hardwareConcurrency && nav.hardwareConcurrency <= 2) return true
  if (nav.deviceMemory && nav.deviceMemory <= 2) return true
  return false
}

/** 3D si WebGL dispo, machine correcte et pas de préférence « économie de magie ». */
export function canUse3D(): boolean {
  return hasWebGL() && !isLowPowerDevice() && !getLowPowerPref()
}

/** Nombre de particules adapté à la machine. */
export function particleBudget(base: number): number {
  const cores = navigator.hardwareConcurrency || 4
  const factor = cores >= 8 ? 1 : cores >= 4 ? 0.6 : 0.35
  const small = window.innerWidth < 768 ? 0.5 : 1
  return Math.round(base * factor * small)
}
