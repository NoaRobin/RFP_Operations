/** Monogramme MERIDIAN : un globe, deux méridiens, un point champagne (la donnée qui compte). */
export function MeridianMark({ className = 'size-8' }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <defs>
        <linearGradient id="mm-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#efe2c4" />
          <stop offset="1" stopColor="#8fa6c3" />
        </linearGradient>
      </defs>
      <circle cx="16" cy="16" r="13" fill="none" stroke="url(#mm-g)" strokeWidth="1.6" />
      <ellipse cx="16" cy="16" rx="6" ry="13" fill="none" stroke="url(#mm-g)" strokeWidth="1.1" opacity=".8" />
      <path d="M3 16h26" stroke="url(#mm-g)" strokeWidth=".9" opacity=".55" />
      <circle cx="22" cy="10.5" r="2.2" fill="#e3cfa1" />
    </svg>
  )
}
