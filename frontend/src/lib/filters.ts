import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

export type Filters = {
  mode: number
  season_from?: number
  season_to?: number
  hero?: number
  map_id?: number
  with: string[]
}

function parseFilters(query: string): Filters {
  const params = new URLSearchParams(query)
  const num = (k: string) => {
    const v = params.get(k)
    return v && /^-?\d+$/.test(v) ? Number(v) : undefined
  }
  return {
    mode: num('mode') ?? 2, season_from: num('season_from'), season_to: num('season_to'),
    hero: num('hero'), map_id: num('map_id'), with: params.getAll('with'),
  }
}

export function useFilters() {
  const [params, setParams] = useSearchParams()
  const query = params.toString()
  const filters = useMemo(() => parseFilters(query), [query])
  const set = useCallback((patch: Record<string, string | number | undefined>) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      for (const [k, v] of Object.entries(patch)) {
        if (v === undefined || v === '') next.delete(k)
        else next.set(k, String(v))
      }
      return next
    })
  }, [setParams])
  const setWith = useCallback((hashes: string[]) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete('with')
      hashes.forEach((h) => next.append('with', h))
      return next
    })
  }, [setParams])
  return useMemo(() => ({ filters, query, set, setWith }), [filters, query, set, setWith])
}

export const pct = (x: number | null | undefined, digits = 0) => (x == null ? '–' : `${(x * 100).toFixed(digits)}%`)
