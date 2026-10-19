import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

const dateFmt = new Intl.DateTimeFormat('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' })
const dateTimeFmt = new Intl.DateTimeFormat('fr-FR', {
  day: '2-digit',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})

export const formatDate = (iso: string | null | undefined) => (iso ? dateFmt.format(new Date(iso)) : '—')
export const formatDateTime = (iso: string | null | undefined) => (iso ? dateTimeFmt.format(new Date(iso)) : '—')

export function formatRelative(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return '—'
  const diff = (now.getTime() - new Date(iso).getTime()) / 1000
  if (diff < 0) return `dans ${formatDuration(-diff * 1000)}`
  if (diff < 45) return "à l'instant"
  if (diff < 3600) return `il y a ${Math.round(diff / 60)} min`
  if (diff < 86400) return `il y a ${Math.round(diff / 3600)} h`
  if (diff < 86400 * 7) return `il y a ${Math.round(diff / 86400)} j`
  return formatDate(iso)
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—'
  if (ms < 1000) return `${Math.round(ms)} ms`
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)} s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} min ${Math.round(s % 60)} s`
  return `${Math.floor(m / 60)} h ${m % 60} min`
}

export function formatMoney(amount: string | number | null | undefined, currency: string | null | undefined): string {
  if (amount === null || amount === undefined) return 'Non précisé'
  const n = typeof amount === 'string' ? Number(amount) : amount
  try {
    return new Intl.NumberFormat('fr-FR', { style: 'currency', currency: currency || 'EUR', maximumFractionDigits: 0 }).format(n)
  } catch {
    return `${n} ${currency ?? ''}`.trim()
  }
}

export const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join('')

export function newIdempotencyKey(): string {
  const c: Crypto = globalThis.crypto
  if (typeof c.randomUUID === 'function') return c.randomUUID()
  // Repli (contextes non sécurisés, ex. HTTP) : UUID v4 à partir de getRandomValues.
  const b = c.getRandomValues(new Uint8Array(16))
  b[6] = (b[6]! & 0x0f) | 0x40
  b[8] = (b[8]! & 0x3f) | 0x80
  const h = [...b].map((x) => x.toString(16).padStart(2, '0'))
  return `${h.slice(0, 4).join('')}-${h.slice(4, 6).join('')}-${h.slice(6, 8).join('')}-${h.slice(8, 10).join('')}-${h.slice(10).join('')}`
}
