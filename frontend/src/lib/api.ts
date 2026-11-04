import { useEffect, useState } from 'react'

export type Stat = {
  games: number; draws: number; n: number; wins: number
  rate: number | null; lo: number; hi: number; enough: boolean; kda: number | null
}
export type Hero = { id: number; name: string; icon: string | null; role: string }
export type MapInfo = { id: number; name: string; place: string; mode: string | null; icon: string | null }

export type Shell = {
  has_data: boolean
  modes: { id: number; label: string; matches: number }[]
  heroes: Hero[]
  maps: MapInfo[]
  seasons: { id: number; label: string; when: string }[]
  players: { id: string; name: string }[]
}

export type HeroRow = Hero & {
  career: number
  mine: Stat | null
  meta: { win: number | null; pick: number | null; ban: number | null } | null
}
export type HeroesData = {
  heroes: HeroRow[]
  meta_label: string | null
  stands: {
    checked: number; flagged: number
    findings: { title: string; direction: 'up' | 'down'; rate: number; base: number; n: number; hero: Hero | null }[]
  }
}

export type MapRow = MapInfo & Stat & { first_season: number | null; last_season: number | null; minutes: number | null }
export type MapsData = {
  maps: MapRow[]
  grid: { heroes: (Hero & { games: number })[]; maps: MapInfo[]; cells: Record<string, Stat> }
  min_games: number
}

export async function getJson<T>(path: string): Promise<T> {
  return (await fetch(path)).json() as Promise<T>
}

/** POST JSON to the app. The header is what the server checks (see web/guard.py). */
export function postJson(path: string, body: unknown): Promise<Response> {
  return fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'rivals-atlas' },
    body: JSON.stringify(body),
  })
}

export function useApi<T>(path: string, query: string): { data: T | null; error: string | null; loading: boolean } {
  const [state, setState] = useState<{ key: string; data: T | null; error: string | null }>({ key: '', data: null, error: null })
  const key = `${path}?${query}`
  useEffect(() => {
    let live = true
    fetch(`/api/${path}?${query}`)
      .then((r) => (r.ok ? (r.json() as Promise<T>) : Promise.reject(new Error(`${r.status} ${r.statusText}`))))
      .then((data) => live && setState({ key, data, error: null }))
      .catch((e: Error) => live && setState({ key, data: null, error: e.message }))
    return () => { live = false }
  }, [key, path, query])
  // keep showing the previous data while a new filter loads
  return { data: state.data, error: state.key === key ? state.error : null, loading: state.key !== key }
}

export type Edge = Hero & { n: number; rate: number; lo: number; hi: number }
export type HeroDetail = {
  hero: Hero
  career: number
  mine: Stat | null
  meta_label: string | null
  meta: { group: { win: number | null; pick: number | null; ban: number | null }; all: { win: number | null; pick: number | null; ban: number | null } | null } | null
  seasons: ({ label: string } & Omit<Stat, 'games' | 'draws' | 'kda'>)[]
  bench: {
    items: { metric: string; tracked: number; others: number; others_median: number; beats_share: number | null; lower_is_better: boolean }[]
    tracked_matches: number; other_lines: number; rate: number | null; n: number; others_rate: number | null; enough: boolean
  } | null
  maps: (MapInfo & Stat)[]
  with: { best: Edge[]; worst: Edge[] }
  against: { best: Edge[]; worst: Edge[] }
  teamups: { heroes: Hero[]; win: number; matches: number }[]
  recent: { played_at: number; map: MapInfo | null; result: string; k: number; d: number; a: number; add_score: number | null }[]
}

export type OverviewData = {
  has_data: boolean
  total: Stat
  losses: number
  top_heroes: (Hero & { career: number; mine: Stat })[]
  rank: { tier: string; score: number; peak: string; level: number } | null
  journey: {
    points: { t: number; score: number; delta: number | null; level: number; tier: string; season: number; ladder: string; result: string }[]
    tiers: { level: number; floor: number; label: string }[]
    seasons: { t: number; season: number; label: string }[]
  }
  facts: { kind: string; label: string; value: string; sub: string; data: Record<string, number | string> }[]
  by_season: { season: number; label: string; wins: number; losses: number; rate: number | null }[]
  form: string[]
  roles: { role: string; games: number }[]
}

export type Bucket = { label: string; n: number; wins: number; rate: number | null; lo: number; hi: number; enough: boolean }
export type PatternsData = {
  cards: { id: string; title: string; note: string; buckets: Bucket[]; clear: boolean; lead: string; detail: string; caveat: string }[]
  n: number; mode_n: number; mode_label: string; min_n: number
  heat?: { days: string[]; blocks: string[]; cells: { d: number; b: number; games: number; n: number; wins: number; rate: number | null; lo: number; hi: number; enough: boolean }[] }
  sessions?: { t: number; games: { r: string; t: number }[] }[]
  days?: { day: string; games: number; wins: number; losses: number }[]
}

export type SquadData = {
  ticked: string[]
  max_party: number
  cols: { id: string; name: string }[]
  regulars: (Stat & { id: string; name: string; last_played: number })[]
  combos: (Stat & { members: string[]; kind: string; names: string[] })[]
}

export type DataInfo = {
  inv: {
    raw: { matches: number; history: number; player: boolean; meta: boolean }
    db: { matches: number; modes: Record<string, number>; seasons: number; players: number; named: number; no_history: number
      player_lines: number; hero_lines: number; bans: number; mb: number }
    derived: { edges: number; meta_heroes: number; meta_teamups: number; meta_age_h: number | null }
  }
  notice: string; profile: string; consented: boolean; matches: number
}
export type FetchJob = {
  state: 'idle' | 'running' | 'done' | 'error'; stage?: string; done?: number; total?: number; message?: string
  error?: string; result?: { imported: number }
}

export type Opt = { value: number | string; label: string }
export type Tally = { label: string; games: number; n: number; wins: number; rate: number | null; lo: number; hi: number; enough: boolean }
export type ExploreData = {
  spec: Record<string, number | string>
  group_by: string | null
  asked: boolean
  error: string
  graph_stale: boolean
  chips: { label: string; drop: string }[]
  choices: Record<'heroes' | 'maps' | 'seasons' | 'roles' | 'blocks' | 'weekdays' | 'positions' | 'regulars' | 'groups', Opt[]>
  default_min?: number
  teammates: Opt[]
  result: null | {
    total: Omit<Tally, 'label' | 'games'>
    games: number; draws: number; group_title: string
    groups: Tally[]
    combos?: (Tally & { ids: string[]; name: string })[]
    panels: {
      heroes: (Tally & { id: number; icon: string | null; role: string })[]
      maps: (Tally & { id: number; icon: string | null })[]
      roles: Tally[]; seasons: Tally[]
      heat: Tally[][]; weekdays: string[]; blocks: string[]
      trend: null | { points: { week: number; rate: number; n: number }[] }
    }
  }
}

export type GraphNode = { id: number; name: string; icon: string | null; kind: 'hero' | 'map'; games: number; n: number; rate: number | null; lo: number | null; hi: number | null; linked: boolean }
export type GraphEdge = { source: number; target: number; n: number; wins: number; lo: number; hi: number; rate: number; kind: string }
export type GraphData = { rel: string; min_n: number; nodes: GraphNode[]; edges: GraphEdge[] }

export type AskCall = { tool: string; cypher: string | null; label: string; n: number; text: string; rows: Record<string, string | number | null>[] }
export type AskJob = {
  state: 'running' | 'done' | 'error'; question: string; seconds: number; error?: string
  calls: AskCall[]; checked: { text: string; matches: string[] }[]; removed: number
  framing?: string; unverified?: string[]; model?: string
}
export type AskInfo = { model: string; examples: string[] }

export type InsightRow = {
  tool: string; label: string; n: number; wins: number | null
  rate: number | null; lo: number; hi: number; enough: boolean
  mode: string; season: string | null; earlier: boolean
  hero?: { id: number; name: string; icon: string | null }
  map?: { name: string; icon: string | null }
  position?: number
  teammate?: { name: string; present: boolean }
  enemy?: { id: number; name: string; icon: string | null }
}

export type Observation = { agent?: string; text: string; relation: string; badge: string; evidence: InsightRow[] }

export type InsightsData = {
  data: null | {
    generated_at: number; model: string; scope: string; matches: number
    observations: Observation[]; dropped: string[]
    last_error?: string
  }
  stale: boolean
  job: { state: 'idle' | 'running' | 'done' | 'error'; error?: string }
}
