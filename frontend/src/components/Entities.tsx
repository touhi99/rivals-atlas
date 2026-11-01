import { Fragment, useMemo, type ReactNode } from 'react'
import { HeroFace } from '@/components/bits'
import type { Shell } from '@/lib/api'

/** Turns hero names in a piece of text into portrait chips and **bold** into bold, so answers show the people and heroes
 *  they talk about. The names and icons are the app's own (the same lists the filters use). */
export function useEntities(shell: Shell | null) {
  return useMemo(() => {
    const map = new Map<string, { name: string; icon: string | null }>()
    shell?.heroes.forEach((h) => map.set(h.name.toLowerCase(), h))
    const maps = new Map<string, { name: string; place: string; icon: string | null }>()
    shell?.maps.forEach((m) => maps.set(m.name.toLowerCase(), m))
    const names = [...map.keys()].sort((a, b) => b.length - a.length)
    const re = names.length ? new RegExp(`(\\*\\*[^*]+\\*\\*|${names.map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi') : null
    return { map, maps, re }
  }, [shell])
}

export function Chip({ name, icon, size = 16 }: { name: string; icon: string | null; size?: number }) {
  return (
    <span className="mx-0.5 inline-flex items-center gap-1 rounded-full bg-muted/70 py-px pl-px pr-2 align-middle text-[0.9em] font-medium">
      <HeroFace hero={{ name, icon }} size={size} />{name}
    </span>
  )
}

export function Rich({ text, ent }: { text: string; ent: ReturnType<typeof useEntities> }) {
  if (!ent.re) return <>{text}</>
  const parts = text.split(ent.re)
  const out: ReactNode[] = parts.map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**')) {
      const inner = p.slice(2, -2)
      const h = ent.map.get(inner.toLowerCase())
      return h ? <Chip key={i} name={h.name} icon={h.icon} /> : <b key={i}>{inner}</b>
    }
    const h = ent.map.get(p.toLowerCase())
    return h ? <Chip key={i} name={h.name} icon={h.icon} /> : <Fragment key={i}>{p}</Fragment>
  })
  return <>{out}</>
}
