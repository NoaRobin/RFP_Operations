/** Logo « RFP pas envie de travailler » : un petit livre qui détale (jambes, goutte de sueur), contour d'encre. */
export function AppMark({ className = 'size-8' }: { className?: string }) {
  return (
    <svg viewBox="0 0 40 40" className={className} aria-hidden="true">
      <path d="M15 31 l-4 6 M24 31 l5 5" stroke="#1b1530" strokeWidth="2.6" strokeLinecap="round" />
      <rect x="9" y="4" width="22" height="28" rx="3" fill="#7c5cff" stroke="#1b1530" strokeWidth="2.4" />
      <rect x="27" y="6" width="4" height="24" rx="1" fill="#fff" stroke="#1b1530" strokeWidth="1.8" />
      <ellipse cx="16" cy="13.5" rx="3" ry="3.6" fill="#fff" stroke="#1b1530" strokeWidth="1.6" />
      <ellipse cx="23" cy="13.5" rx="3" ry="3.6" fill="#fff" stroke="#1b1530" strokeWidth="1.6" />
      <circle cx="15" cy="14" r="1.4" fill="#1b1530" />
      <circle cx="22" cy="14" r="1.4" fill="#1b1530" />
      <ellipse cx="19.5" cy="22" rx="2" ry="2.8" fill="#1b1530" />
      <path d="M35 6 q-3 4 0 6 q3 -2 0 -6z" fill="#7cd3ff" stroke="#1b1530" strokeWidth="1.2" />
      <path d="M3 18 h4 M2 23 h5 M4 28 h3" stroke="#1b1530" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}
