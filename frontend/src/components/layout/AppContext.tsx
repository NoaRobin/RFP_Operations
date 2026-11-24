import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { api } from '../../lib/api'
import type { FabricStatus, Health } from '../../lib/types'
import { CommandPalette } from '../CommandPalette'
import { FabricDialog } from '../FabricDialog'
import { SuggestionDialog } from '../SuggestionDialog'
import { UserDialog } from '../UserDialog'

interface AppContextValue {
  health: Health | null
  fabric: FabricStatus | null
  openFabric: () => void
  retryFabric: () => void
  openSuggest: () => void
  openUser: () => void
  openPalette: () => void
}

const Ctx = createContext<AppContextValue>({ health: null, fabric: null, openFabric: () => {}, retryFabric: () => {}, openSuggest: () => {}, openUser: () => {}, openPalette: () => {} })
export const useApp = () => useContext(Ctx)

export const isMac = () => typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)

export function AppProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null)
  const [suggest, setSuggest] = useState(false)
  const [user, setUser] = useState(false)
  const [palette, setPalette] = useState(false)
  const [fabric, setFabric] = useState<FabricStatus | null>(null)
  const [fabricOpen, setFabricOpen] = useState(false)

  useEffect(() => {
    let alive = true
    const load = () => {
      api.health().then((h) => alive && setHealth(h)).catch(() => alive && setHealth(null))
      api.fabric.status().then((f) => alive && setFabric(f)).catch(() => undefined)
    }
    load()
    const id = window.setInterval(load, 60_000)
    return () => {
      alive = false
      window.clearInterval(id)
    }
  }, [])

  // Connexion automatique à Fabric au lancement : suivi rapproché, puis la page est rechargée sur les vraies données.
  const wasConnecting = useRef(false)
  useEffect(() => {
    if (fabric?.state === 'connecting') {
      wasConnecting.current = true
      const id = window.setInterval(() => { api.fabric.status().then(setFabric).catch(() => undefined) }, 2500)
      return () => window.clearInterval(id)
    }
    if (wasConnecting.current && fabric?.state === 'connected' && fabric.auto) window.location.reload()
    if (fabric) wasConnecting.current = false
    return undefined
  }, [fabric])

  // ⌘K / Ctrl+K partout, même dans un champ de saisie.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPalette((p) => !p)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const openSuggest = useCallback(() => setSuggest(true), [])
  const openUser = useCallback(() => setUser(true), [])
  const openPalette = useCallback(() => setPalette(true), [])
  const closePalette = useCallback(() => setPalette(false), [])
  const openFabric = useCallback(() => setFabricOpen(true), [])
  const retryFabric = useCallback(() => { api.fabric.retry().then(setFabric).catch(() => undefined) }, [])
  const onFabricChange = useCallback((next: FabricStatus) => {
    setFabric(next)
    api.health().then(setHealth).catch(() => undefined)
  }, [])

  return (
    <Ctx.Provider value={{ health, fabric, openFabric, retryFabric, openSuggest, openUser, openPalette }}>
      {children}
      <SuggestionDialog open={suggest} onClose={() => setSuggest(false)} />
      <UserDialog open={user} onClose={() => setUser(false)} />
      <FabricDialog open={fabricOpen} onClose={() => setFabricOpen(false)} status={fabric} onChange={onFabricChange} />
      <CommandPalette open={palette} onClose={closePalette} onSuggest={openSuggest} onUser={openUser} onFabric={openFabric} />
    </Ctx.Provider>
  )
}
