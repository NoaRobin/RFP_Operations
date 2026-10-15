import { useEffect, useRef, type ReactNode } from 'react'
import { X } from 'lucide-react'
import { gsap } from '../../motion/gsap'
import { d, dist, ease } from '../../motion/tokens'
import { IconButton } from './Button'
import { texts } from '../../content/texts'

/** Boîte de dialogue native (<dialog>) : piège du focus, Échap et retour du focus gratuits. */
export function Dialog({
  open, onClose, title, children, footer, size = 'md',
}: { open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode; size?: 'md' | 'lg' }) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) {
      dialog.showModal()
      gsap.fromTo(dialog, { opacity: 0, y: dist('enter'), scale: 0.97 }, { opacity: 1, y: 0, scale: 1, duration: d('base'), ease: ease.out })
    } else if (!open && dialog.open) {
      gsap.to(dialog, { opacity: 0, y: dist('nudge'), duration: d('fast'), ease: ease.in, onComplete: () => dialog.close() })
    }
  }, [open])

  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault()
        onClose()
      }}
      onClick={(e) => e.target === ref.current && onClose()}
      aria-labelledby="dialog-title"
      className={`glass m-auto w-[92vw] ${size === 'lg' ? 'max-w-[46rem]' : 'max-w-[32rem]'} rounded-[var(--radius-card)] p-0 text-fg shadow-[var(--shadow-deep)] backdrop:bg-transparent`}
    >
      {open && (
        <div className="flex flex-col max-h-[85vh]">
          <header className="flex items-center justify-between gap-4 px-6 pt-6">
            <h2 id="dialog-title" className="text-2xl">{title}</h2>
            <IconButton label={texts.common.close} onClick={onClose}><X size={18} /></IconButton>
          </header>
          <div className="px-6 py-5 overflow-y-auto">{children}</div>
          {footer && <footer className="flex flex-wrap justify-end gap-3 px-6 pb-6">{footer}</footer>}
        </div>
      )}
    </dialog>
  )
}
