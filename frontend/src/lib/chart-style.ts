export const WIN = '#10b981'
export const LOSS = '#f97316'
export const AXIS = { fontSize: 11, fill: 'var(--muted-foreground)' }
export const TIP = { background: 'var(--popover)', color: 'var(--popover-foreground)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }

export function timeAxis(min: number, max: number, count = 6) {
  const span = (max - min) / 86400
  const ticks = Array.from({ length: count }, (_, i) => Math.round(min + ((max - min) * i) / (count - 1)))
  const tickFormatter = (t: number) => new Date(t * 1000).toLocaleDateString(undefined, span > 200 ? { month: 'short', year: 'numeric' } : span > 20 ? { day: 'numeric', month: 'short' } : { day: 'numeric', month: 'short' })
  return { ticks, tickFormatter }
}
