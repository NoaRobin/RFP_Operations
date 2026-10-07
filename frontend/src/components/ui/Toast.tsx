import { createContext, useCallback, useContext, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { CheckCircle2, Info, Sparkles, TriangleAlert, X } from 'lucide-react'
import { gsap } from '../../motion/gsap'
import { d, dist, ease } from '../../motion/tokens'

type Tone = 'success' | 'error' | 'info' | 'magic'
interface ToastItem { id: number; tone: Tone; title: string; body?: string }

const ToastContext = createContext<(tone: Tone, title: string, body?: string) => void>(() => {})

export const useToast = () => useContext(ToastContext)

const ICON = { success: CheckCircle2, error: TriangleAlert, info: Info, magic: Sparkles }
const TONE = {
  success: 'text-success',
  error: 'text-danger',
  info: 'text-info',
  magic: 'text-champagne-300',
}

function ToastView({ item, onClose }: { item: ToastItem; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    gsap.fromTo(ref.current, { opacity: 0, x: dist('enter'), scale: 0.96 }, { opacity: 1, x: 0, scale: 1, duration: d('base'), ease: ease.spring })
  }, [])
  const Icon = ICON[item.tone]
  return (
    <div ref={ref} className="glass pointer-events-auto flex w-[min(92vw,24rem)] items-start gap-3 rounded-2xl p-4 shadow-[var(--shadow-deep)]">
      <Icon className={`mt-0.5 shrink-0 ${TONE[item.tone]}`} size={20} aria-hidden="true" />
      <div className="flex-1 min-w-0">
        <p className="font-semibold text-ivory">{item.title}</p>
        {item.body && <p className="mt-1 text-sm text-mist">{item.body}</p>}
      </div>
      <button onClick={onClose} aria-label="Fermer la notification" className="text-haze hover:text-ivory"><X size={16} /></button>
    </div>
  )
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const counter = useRef(0)
  const remove = useCallback((id: number) => setItems((all) => all.filter((t) => t.id !== id)), [])
  const push = useCallback(
    (tone: Tone, title: string, body?: string) => {
      const id = ++counter.current
      setItems((all) => [...all.slice(-3), { id, tone, title, body }])
      window.setTimeout(() => remove(id), tone === 'error' ? 9000 : 5000)
    },
    [remove],
  )
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div aria-live="polite" aria-atomic="false" className="pointer-events-none fixed bottom-5 right-5 z-[80] flex flex-col items-end gap-3">
        {items.map((item) => <ToastView key={item.id} item={item} onClose={() => remove(item.id)} />)}
      </div>
    </ToastContext.Provider>
  )
}
