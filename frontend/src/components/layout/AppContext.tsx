import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
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
  openSuggest: () => void
  openUser: () => void
  openPalette: () => void
}

const Ctx = createContext<AppContextValue>({ health: null, fabric: null, openFabric: () => {}, openSuggest: () => {}, openUser: () => {}, openPalette: () => {} })
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
  const onFabricChange = useCallback((next: FabricStatus) => {
    setFabric(next)
    api.health().then(setHealth).catch(() => undefined)
  }, [])

  return (
    <Ctx.Provider value={{ health, fabric, openFabric, openSuggest, openUser, openPalette }}>
      {children}
      <SuggestionDialog open={suggest} onClose={() => setSuggest(false)} />
      <UserDialog open={user} onClose={() => setUser(false)} />
      <FabricDialog open={fabricOpen} onClose={() => setFabricOpen(false)} status={fabric} onChange={onFabricChange} />
      <CommandPalette open={palette} onClose={closePalette} onSuggest={openSuggest} onUser={openUser} onFabric={openFabric} />
    </Ctx.Provider>
  )
}
