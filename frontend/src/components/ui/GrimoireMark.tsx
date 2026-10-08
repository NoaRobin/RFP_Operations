/** Logo GRIMOIRE : un livre de sorts cartoon, contour d'encre, étoile jaune sur la couverture. */
export function GrimoireMark({ className = 'size-8' }: { className?: string }) {
  return (
    <svg viewBox="0 0 40 40" className={className} aria-hidden="true">
      <path d="M8 7.5 Q8 5 10.5 5 H31 a2 2 0 0 1 2 2 V31 a2 2 0 0 1 -2 2 H11 a3 3 0 0 0 -3 3 Z" fill="#7c5cff" stroke="#1b1530" strokeWidth="2.4" strokeLinejoin="round" />
      <path d="M8 36 a3 3 0 0 1 3 -3 H33 V36.5 H11 A1.8 1.8 0 0 1 8 36 Z" fill="#fff" stroke="#1b1530" strokeWidth="2.4" strokeLinejoin="round" />
      <path d="M12 5.5 V32.5" stroke="#1b1530" strokeWidth="1.6" opacity=".35" />
      <path d="M22 11.2 l2.1 4.3 4.7 .7 -3.4 3.3 .8 4.7 -4.2 -2.2 -4.2 2.2 .8 -4.7 -3.4 -3.3 4.7 -.7z" fill="#ffd23f" stroke="#1b1530" strokeWidth="1.8" strokeLinejoin="round" />
      <circle cx="29.5" cy="8.5" r="1.1" fill="#fff" />
    </svg>
  )
}
