import { useRef, useState } from 'react'
import { UploadCloud } from 'lucide-react'
import { texts } from '../../content/texts'
import { gsap } from '../../motion/gsap'
import { d, ease } from '../../motion/tokens'

interface DropzoneProps {
  onFile: (file: File) => void
  busy: boolean
  accept?: string
  title?: string
  body?: string
  activeTitle?: string
  busyTitle?: string
  compact?: boolean
}

export function Dropzone({
  onFile, busy, accept = '.xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  title = texts.atelier.dropTitle, body = texts.atelier.dropBody, activeTitle = texts.atelier.dropActive,
  busyTitle = texts.atelier.analyzing, compact = false,
}: DropzoneProps) {
  const input = useRef<HTMLInputElement>(null)
  const zone = useRef<HTMLDivElement>(null)
  const [active, setActive] = useState(false)

  const pulse = (on: boolean) => {
    setActive(on)
    if (zone.current) gsap.to(zone.current, { scale: on ? 1.015 : 1, duration: d('base'), ease: on ? ease.spring : ease.out })
  }

  return (
    <div
      ref={zone}
      onDragOver={(e) => {
        if (!e.dataTransfer.types.includes('Files')) return
        e.preventDefault()
        if (!active) pulse(true)
      }}
      onDragLeave={() => pulse(false)}
      onDrop={(e) => {
        e.preventDefault()
        pulse(false)
        const file = e.dataTransfer.files[0]
        if (file) onFile(file)
      }}
      className={`relative overflow-hidden rounded-[calc(var(--radius-card)*1.4)] border-[3px] border-dashed border-fg transition-colors duration-[var(--duration-base)] ${
        active ? 'bg-mint-400/25' : 'bg-card hover:bg-sun-400/15'}`}
    >
      <button
        type="button"
        disabled={busy}
        onClick={() => input.current?.click()}
        className={`flex w-full flex-col items-center gap-4 px-6 text-center disabled:cursor-wait ${compact ? 'py-8' : 'py-16'}`}
      >
        <span className={`grid size-20 place-items-center rounded-full border-[2.5px] border-fg bg-sun-400 text-fg shadow-[3px_3px_0_0_var(--color-fg)] ${busy ? 'animate-bounce' : 'animate-float'}`}>
          <UploadCloud size={36} aria-hidden="true" />
        </span>
        <span className="font-display text-2xl sm:text-3xl text-fg">{busy ? busyTitle : active ? activeTitle : title}</span>
        <span className="text-fg-2">{body}</span>
      </button>
      <input
        ref={input}
        type="file"
        accept={accept}
        className="sr-only"
        tabIndex={-1}
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) onFile(file)
          e.target.value = ''
        }}
      />
    </div>
  )
}
