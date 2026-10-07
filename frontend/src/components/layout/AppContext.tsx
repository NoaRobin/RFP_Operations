import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api } from '../../lib/api'
import type { Health } from '../../lib/types'
import { SuggestionDialog } from '../SuggestionDialog'
import { UserDialog } from '../UserDialog'

interface AppContextValue {
  health: Health | null
  openSuggest: () => void
  openUser: () => void
}

const Ctx = createContext<AppContextValue>({ health: null, openSuggest: () => {}, openUser: () => {} })
export const useApp = () => useContext(Ctx)

export function AppProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null)
  const [suggest, setSuggest] = useState(false)
  const [user, setUser] = useState(false)

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

  const openSuggest = useCallback(() => setSuggest(true), [])
  const openUser = useCallback(() => setUser(true), [])

  return (
    <Ctx.Provider value={{ health, openSuggest, openUser }}>
      {children}
      <SuggestionDialog open={suggest} onClose={() => setSuggest(false)} />
      <UserDialog open={user} onClose={() => setUser(false)} />
    </Ctx.Provider>
  )
}
