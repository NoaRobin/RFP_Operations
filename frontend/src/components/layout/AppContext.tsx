import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api } from '../../lib/api'
import type { Health } from '../../lib/types'
import { CommandPalette } from '../CommandPalette'
import { SuggestionDialog } from '../SuggestionDialog'
import { UserDialog } from '../UserDialog'

interface AppContextValue {
  health: Health | null
  openSuggest: () => void
  openUser: () => void
  openPalette: () => void
}

const Ctx = createContext<AppContextValue>({ health: null, openSuggest: () => {}, openUser: () => {}, openPalette: () => {} })
export const useApp = () => useContext(Ctx)

export const isMac = () => typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)

export function AppProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null)
  const [suggest, setSuggest] = useState(false)
  const [user, setUser] = useState(false)
  const [palette, setPalette] = useState(false)

  useEffect(() => {
    let alive = true
    const load = () => api.health().then((h) => alive && setHealth(h)).catch(() => alive && setHealth(null))
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

  return (
    <Ctx.Provider value={{ health, openSuggest, openUser, openPalette }}>
      {children}
      <SuggestionDialog open={suggest} onClose={() => setSuggest(false)} />
      <UserDialog open={user} onClose={() => setUser(false)} />
      <CommandPalette open={palette} onClose={closePalette} onSuggest={openSuggest} onUser={openUser} />
    </Ctx.Provider>
  )
}
