import { useMemo } from 'react'
import type { Shell } from '@/lib/api'

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

export type Entities = ReturnType<typeof useEntities>
