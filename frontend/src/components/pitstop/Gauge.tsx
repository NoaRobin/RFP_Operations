/** Cadran de télémétrie du stand : arc gradué, aiguille, valeur en chiffres. L'aiguille ne bouge pas en mouvement réduit. */
export function Gauge({ value, label, hint, display }: { value: number | null; label: string; hint?: string; display?: string }) {
  const v = value == null ? 0 : Math.max(0, Math.min(1, value))
  const angle = -120 + 240 * v
  const r = 46
  const arc = (from: number, to: number) => {
    const p = (a: number) => [60 + r * Math.cos(((a - 90) * Math.PI) / 180), 64 + r * Math.sin(((a - 90) * Math.PI) / 180)]
    const [x1, y1] = p(from), [x2, y2] = p(to)
    return `M ${x1} ${y1} A ${r} ${r} 0 ${to - from > 180 ? 1 : 0} 1 ${x2} ${y2}`
  }
  const tone = v >= 0.66 ? 'var(--color-mint-400)' : v >= 0.33 ? 'var(--color-magic-500)' : 'var(--color-bubble-400)'
  return (
    <figure className="flex flex-col items-center text-center">
      <svg viewBox="0 0 120 100" className="w-full max-w-[11rem]" role="img" aria-label={`${label} : ${display ?? (value == null ? '—' : `${Math.round(v * 100)} %`)}`}>
        <path d={arc(-120, 120)} stroke="var(--color-card-3)" strokeWidth="12" fill="none" strokeLinecap="round" />
        {value != null && <path d={arc(-120, angle)} stroke={tone} strokeWidth="12" fill="none" strokeLinecap="round" />}
        {[-120, -60, 0, 60, 120].map((a) => (
          <line key={a} x1="60" y1="14" x2="60" y2="22" stroke="var(--color-fg)" strokeWidth="2.5" transform={`rotate(${a} 60 64)`} />
        ))}
        <g className="motion-safe:transition-transform motion-safe:duration-700" style={{ transform: `rotate(${angle}deg)`, transformOrigin: '60px 64px' }}>
          <line x1="60" y1="64" x2="60" y2="26" stroke="var(--color-fg)" strokeWidth="4" strokeLinecap="round" />
        </g>
        <circle cx="60" cy="64" r="7" fill="var(--color-fg)" />
        <text x="60" y="94" textAnchor="middle" className="font-mono" fontSize="15" fontWeight="700" fill="var(--color-fg)">
          {display ?? (value == null ? '—' : `${Math.round(v * 100)} %`)}
        </text>
      </svg>
      <figcaption className="mt-1 font-display text-sm font-semibold leading-tight">{label}</figcaption>
      {hint && <p className="mt-0.5 max-w-[14rem] text-xs font-semibold text-fg-3">{hint}</p>}
    </figure>
  )
}
