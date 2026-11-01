import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from 'recharts'
import { HeroFace, MapBanner, Panel, WinBar } from '@/components/bits'
import { AXIS, LOSS, TIP, WIN } from '@/components/charts'
import Layout from '@/components/Layout'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useApi, type MapsData } from '@/lib/api'
import { pct, useFilters } from '@/lib/filters'
import { cn } from '@/lib/utils'

const MODE_TONE: Record<string, string> = {
  Convoy: 'bg-amber-500/80', Domination: 'bg-lime-600/80', Convergence: 'bg-teal-500/80', 'Doom Match': 'bg-rose-500/80',
}

function ModeTag({ mode }: { mode: string | null }) {
  if (!mode) return null
  return <span className={cn('rounded px-1.5 py-0.5 text-[10px] font-semibold text-white', MODE_TONE[mode] ?? 'bg-muted-foreground/60')}>{mode}</span>
}

export default function MapsPage() {
  const { query, filters } = useFilters()
  const { data, error, loading } = useApi<MapsData>('maps', query)
  const to = (patch: string) => {
    const p = new URLSearchParams(query)
    for (const [k, v] of new URLSearchParams(patch)) p.set(k, v)
    return `/maps?${p.toString()}`
  }

  const cellLink = (hero: number, map: number) => {
    const p = new URLSearchParams(query)
    p.set('hero', String(hero)); p.set('map_id', String(map))
    return `/maps?${p.toString()}`
  }

  const rateBars = (data?.maps ?? []).filter((m) => m.enough).map((m) => ({ id: m.id, name: `${m.place}${m.mode ? ` · ${m.mode}` : ''}`, rate: +((m.rate ?? 0) * 100).toFixed(1), n: m.n })).sort((a, b) => b.rate - a.rate)

  return (
    <Layout title="Maps">
      {error && <p className="text-sm text-destructive">Could not load: {error}</p>}
      {!data && !error && <Skeleton className="h-96 w-full" />}
      {data && (
        <div className={cn('flex flex-col gap-6', loading && 'opacity-60 transition-opacity')}>
          <Panel title="Win rate by map" hint="maps with enough decided games · the line is 50%">
            <div className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={rateBars} margin={{ top: 8, right: 8, bottom: 0, left: 40 }}>
                  <CartesianGrid stroke="var(--border)" strokeOpacity={0.4} vertical={false} />
                  <XAxis dataKey="name" tick={AXIS} stroke="var(--border)" interval={0} angle={-35} textAnchor="end" height={96} />
                  <YAxis domain={[30, 70]} tick={AXIS} stroke="var(--border)" width={36} unit="%" />
                  <ReferenceLine y={50} stroke="var(--muted-foreground)" strokeDasharray="4 4" />
                  <RTooltip contentStyle={TIP} cursor={{ fill: 'var(--accent)', opacity: 0.4 }} formatter={(v, _n, i) => [`${v}% in ${(i.payload as { n: number }).n} games`, 'Win rate']} />
                  <Bar dataKey="rate" radius={[4, 4, 0, 0]} isAnimationActive={false}>
                    {rateBars.map((m) => <Cell key={m.id} fill={m.rate >= 50 ? WIN : LOSS} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Panel>
          <Panel title="Maps" hint={`${data.maps.length} layouts · each map id is one map in one game mode`}>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
              {data.maps.map((m) => (
                <Link key={m.id} to={to(`map_id=${m.id}`)} className={cn('group overflow-hidden rounded-xl border border-border/60 bg-background/40 transition hover:border-primary/60 hover:shadow-lg',
                  filters.map_id === m.id && 'border-primary ring-1 ring-primary')}>
                  <div className="relative h-24">
                    <MapBanner map={m} className="h-full w-full transition group-hover:scale-105" />
                    <div className="absolute inset-0 bg-gradient-to-t from-background via-background/30 to-transparent" />
                    <div className="absolute bottom-2 left-3 right-3 flex items-end justify-between">
                      <div className="text-sm font-semibold leading-tight drop-shadow">{m.place}</div>
                      <ModeTag mode={m.mode} />
                    </div>
                  </div>
                  <div className="flex items-center justify-between gap-3 p-3 text-xs text-muted-foreground">
                    <WinBar s={m} width={90} />
                    <span className="tabular-nums">{m.games} games{m.minutes ? ` · ${Math.round(m.minutes)} min` : ''}</span>
                  </div>
                </Link>
              ))}
              {!data.maps.length && <p className="text-sm text-muted-foreground">No maps for this filter.</p>}
            </div>
          </Panel>

          {data.grid.heroes.length > 0 && data.grid.maps.length > 0 && (
            <Panel title="Hero × map" hint={`every cell is the win rate, with the number of games under it · faded cells have under ${data.min_games} decided games, so treat them as a hint · blank = never played · click a cell to filter`}>
              <div className="overflow-x-auto pb-2">
                <div className="grid w-max gap-1" style={{ gridTemplateColumns: `200px repeat(${data.grid.maps.length}, 76px)` }}>
                  <div />
                  {data.grid.maps.map((m) => (
                    <Tooltip key={m.id}>
                      <TooltipTrigger render={<div className="flex flex-col items-center gap-1" />}>
                        <>
                          <MapBanner map={m} className="h-12 w-[76px] rounded-md ring-1 ring-border" />
                          <div className="w-full truncate text-center text-[10px] leading-tight text-muted-foreground">{m.place}</div>
                          <ModeTag mode={m.mode} />
                        </>
                      </TooltipTrigger>
                      <TooltipContent>{m.name}</TooltipContent>
                    </Tooltip>
                  ))}
                  {data.grid.heroes.map((h) => (
                    <div key={h.id} className="contents">
                      <Link to={`/heroes/${h.id}?${query}`} className="flex items-center gap-2.5 pr-2">
                        <HeroFace hero={h} size={32} />
                        <div className="min-w-0 leading-tight">
                          <div className="truncate text-sm font-medium">{h.name}</div>
                          <div className="text-[11px] text-muted-foreground">{h.games} games</div>
                        </div>
                      </Link>
                      {data.grid.maps.map((m) => {
                        const c = data.grid.cells[`${h.id}:${m.id}`]
                        if (!c) return <div key={m.id} className="h-11 rounded-md border border-dashed border-border/30" />
                        const dev = (c.rate ?? 0.5) - 0.5
                        const strength = c.enough ? Math.min(Math.max(Math.abs(dev) * 220, 14), 70) : 12
                        return (
                          <Tooltip key={m.id}>
                            <TooltipTrigger render={<Link to={cellLink(h.id, m.id)}
                                className={cn('flex h-11 flex-col items-center justify-center rounded-md leading-none tabular-nums transition hover:ring-2 hover:ring-primary', !c.enough && 'opacity-60')}
                                style={c.rate != null ? { background: `color-mix(in srgb, ${dev >= 0 ? '#10b981' : '#f97316'} ${strength}%, transparent)` } : undefined} />}>
                              <span className={cn('text-sm', c.enough ? 'font-semibold' : 'font-normal')}>{c.rate != null ? `${Math.round(c.rate * 100)}%` : '–'}</span>
                              <span className="mt-0.5 text-[9px] text-muted-foreground">{c.n} {c.n === 1 ? 'game' : 'games'}</span>
                            </TooltipTrigger>
                            <TooltipContent>
                              {h.name} on {m.name}: {c.wins} wins in {c.n} decided games
                              {c.enough ? ` (${pct(c.rate)}, range ${pct(c.lo)}–${pct(c.hi)})` : ` · under ${data.min_games} games, too few to trust`}
                            </TooltipContent>
                          </Tooltip>
                        )
                      })}
                    </div>
                  ))}
                </div>
              </div>
            </Panel>
          )}
        </div>
      )}
    </Layout>
  )
}
