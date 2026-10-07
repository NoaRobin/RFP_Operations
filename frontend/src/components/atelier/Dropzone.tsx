import { useRef, useState } from 'react'
import { UploadCloud } from 'lucide-react'
import { texts } from '../../content/texts'
import { gsap } from '../../motion/gsap'
import { d, ease } from '../../motion/tokens'

export function Dropzone({ onFile, busy }: { onFile: (file: File) => void; busy: boolean }) {
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
      className={`relative overflow-hidden rounded-[calc(var(--radius-card)*1.4)] border-2 border-dashed transition-colors duration-[var(--duration-base)] ${
        active ? 'border-arcane-400 bg-arcane-400/10' : 'border-gold-400/40 bg-white/[0.02] hover:border-gold-400/80'}`}
    >
      <button
        type="button"
        disabled={busy}
        onClick={() => input.current?.click()}
        className="flex w-full flex-col items-center gap-4 px-6 py-16 text-center disabled:cursor-wait"
      >
        <span className={`grid size-20 place-items-center rounded-full border border-gold-400/40 bg-gold-400/10 text-gold-300 ${busy ? 'animate-pulse' : ''}`}>
          <UploadCloud size={36} aria-hidden="true" />
        </span>
        <span className="font-display text-3xl text-parchment">{busy ? texts.atelier.analyzing : active ? texts.atelier.dropActive : texts.atelier.dropTitle}</span>
        <span className="text-mist">{texts.atelier.dropBody}</span>
      </button>
      <input
        ref={input}
        type="file"
        accept=".xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
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
