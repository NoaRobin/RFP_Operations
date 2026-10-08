/** Préférences locales (par navigateur). Toujours protégées : le stockage peut être indisponible. */
import { useSyncExternalStore } from 'react'

const KEYS = {
  user: 'grimoire.user',
  favorites: 'grimoire.favorites',
  skipIntro: 'grimoire.intro.skip',
  lowPower: 'grimoire.lowPower',
} as const

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key: string, value: string | null) {
  try {
    if (value === null) window.localStorage.removeItem(key)
    else window.localStorage.setItem(key, value)
  } catch {
    /* stockage indisponible : on continue sans mémoire */
  }
  listeners.forEach((l) => l())
}

const listeners = new Set<() => void>()
function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function useStored(key: string): string | null {
  return useSyncExternalStore(subscribe, () => read(key), () => null)
}

/* ------------------------------------------------------------ utilisateur */
export const getUserName = () => read(KEYS.user) ?? ''
export const setUserName = (name: string) => write(KEYS.user, name.trim() || null)
export const useUserName = () => useStored(KEYS.user) ?? ''

/* ------------------------------------------------------------ favoris */
export function useFavorites(): [Set<string>, (id: string) => void] {
  const raw = useStored(KEYS.favorites)
  let set: Set<string>
  try {
    set = new Set<string>(raw ? JSON.parse(raw) : [])
  } catch {
    set = new Set()
  }
  const toggle = (id: string) => {
    const next = new Set(set)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    write(KEYS.favorites, JSON.stringify([...next]))
  }
  return [set, toggle]
}

/* ------------------------------------------------------------ intro */
export const shouldSkipIntro = () => read(KEYS.skipIntro) === '1'
export const setSkipIntro = (skip: boolean) => write(KEYS.skipIntro, skip ? '1' : null)

/* ------------------------------------------------------------ économie de magie */
export const useLowPowerPref = () => useStored(KEYS.lowPower) === '1'
export const setLowPowerPref = (on: boolean) => write(KEYS.lowPower, on ? '1' : null)
export const getLowPowerPref = () => read(KEYS.lowPower) === '1'
