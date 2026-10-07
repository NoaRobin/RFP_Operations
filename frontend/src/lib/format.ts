import { texts } from '../content/texts'

const nf = new Intl.NumberFormat('fr-FR')
const rtf = new Intl.RelativeTimeFormat('fr', { numeric: 'auto' })

export const formatNumber = (n: number, digits = 0) =>
  new Intl.NumberFormat('fr-FR', { maximumFractionDigits: digits, minimumFractionDigits: 0 }).format(n)

export const formatInt = (n: number) => nf.format(Math.round(n))

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return texts.common.unknown
  const s = ms / 1000
  if (s < 1) return `${Math.round(ms)} ms`
  if (s < 60) return `${s.toFixed(1).replace('.', ',')} s`
  const m = Math.floor(s / 60)
  return `${m} min ${Math.round(s % 60).toString().padStart(2, '0')} s`
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return texts.common.unknown
  const date = new Date(iso)
  return date.toLocaleString('fr-FR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return texts.common.unknown
  return new Date(iso).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' })
}

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return texts.common.unknown
  const diff = (new Date(iso).getTime() - Date.now()) / 1000
  const abs = Math.abs(diff)
  if (abs < 60) return rtf.format(Math.round(diff), 'second')
  if (abs < 3600) return rtf.format(Math.round(diff / 60), 'minute')
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), 'hour')
  if (abs < 86400 * 30) return rtf.format(Math.round(diff / 86400), 'day')
  return formatDate(iso)
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} o`
  if (bytes < 1024 ** 2) return `${formatNumber(bytes / 1024, 1)} Ko`
  return `${formatNumber(bytes / 1024 ** 2, 1)} Mo`
}

export const todayIso = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function greeting(): string {
  const h = new Date().getHours()
  if (h < 5) return texts.greeting.night
  if (h < 12) return texts.greeting.morning
  if (h < 18) return texts.greeting.afternoon
  if (h < 23) return texts.greeting.evening
  return texts.greeting.night
}
