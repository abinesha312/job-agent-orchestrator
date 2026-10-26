export function ago(iso: string | null | undefined): string {
  if (!iso) return 'never'
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ''
  const s = Math.max(0, Math.round((Date.now() - t) / 1000))
  if (s < 5) return 'just now'
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

export function clock(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString()
}

export function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? '-' : `${Math.round(v * 100)}%`
}

export function statusTone(status: string | null | undefined): '' | 'ok' | 'warn' | 'bad' {
  switch (status) {
    case 'approved':
    case 'applied':
      return 'ok'
    case 'awaiting_approval':
    case 'tailored':
      return 'warn'
    case 'rejected':
      return 'bad'
    default:
      return ''
  }
}
