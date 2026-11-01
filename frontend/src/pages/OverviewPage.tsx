import { Trophy } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import Highlights from '@/components/Highlights'
import { AXIS, FormStrip, Gauge, LOSS, RoleDonut, TIP, WIN, timeAxis } from '@/components/charts'
import { HeroFace, Mastery, Panel, Spinner, StatTile, WinBar } from '@/components/bits'
import Layout from '@/components/Layout'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useApi, type OverviewData } from '@/lib/api'
import { pct, useFilters } from '@/lib/filters'

const date = (t: number) => new Date(t * 1000).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: '2-digit' })

export default function OverviewPage() {
  const { query, filters } = useFilters()
  const { data: d, error } = useApi<OverviewData>('overview', query)
  const [season, setSeason] = useState<number | 'all' | null>(null)   // null = the latest season until chosen

  const all = useMemo(() => {
    if (!d) return []
    const main = d.journey.points.filter((p) => p.ladder === 'main')
    return main.length ? main : d.journey.points
  }, [d])
  const seasons = d?.journey.seasons ?? []
  const latest = seasons.length ? seasons[seasons.length - 1].season : null
  const prev = seasons.length > 1 ? seasons[seasons.length - 2].season : null
  const pick = season ?? (latest ?? 'all')
  useEffect(() => setSeason(null), [query])
  const points = pick === 'all' ? all : all.filter((p) => p.season === pick)
  const ys = points.map((p) => p.score)
  const lo = Math.min(...ys), hi = Math.max(...ys)
  const tierLines = (d?.journey.tiers ?? []).filter((x) => x.floor >= lo - 120 && x.floor <= hi + 120)
  const tierTicks = pick === 'all' ? tierLines.filter((x) => /\s3$/.test(x.label) || !/\d$/.test(x.label)) : tierLines
  const t = d?.total
  const latestPts = latest != null ? all.filter((p) => p.season === latest) : []
  const latestDelta = latestPts.length > 1 ? latestPts[latestPts.length - 1].score - latestPts[0].score : 0
  const start = points[0]?.score, end = points[points.length - 1]?.score

  return (
    <Layout title="Overview">
      {error && <p className="text-sm text-destructive">Could not load: {error}</p>}
      {!d && !error && <Spinner />}
      {d && !d.has_data && <Panel title="No data yet"><p className="text-sm text-muted-foreground">Open Data, paste a player page address and fetch the match history.</p></Panel>}
      {d && d.has_data && t && t.games === 0 && <Panel title="Nothing here"><p className="text-sm text-muted-foreground">No matches for this filter.</p></Panel>}
      {d && d.has_data && t && t.games > 0 && (
        <>
          <div className="grid gap-4 @xl/main:grid-cols-2 @5xl/main:grid-cols-4">
            <StatTile label="Win rate" value={t.rate != null ? `${(t.rate * 100).toFixed(1)}%` : '–'}
              tone={t.rate != null && t.lo > 0.5 ? 'up' : t.rate != null && t.hi < 0.5 ? 'down' : undefined}
              trend={t.rate != null ? { text: `${t.rate >= 0.5 ? '+' : ''}${((t.rate - 0.5) * 100).toFixed(1)} pts`, dir: t.lo > 0.5 ? 'up' : t.hi < 0.5 ? 'down' : 'flat' } : undefined}
              note={<><b className="text-emerald-400">{t.wins}W</b> <b className="text-orange-400">{d.losses}L</b>{t.draws ? ` ${t.draws}D` : ''}</>}
              sub={`95% range ${pct(t.lo)}–${pct(t.hi)}${t.lo <= 0.5 && 0.5 <= t.hi ? ' · not clearly different from 50%' : ''}`} />
            {filters.mode !== 1 && d.rank && (
              <StatTile label="Rank" value={<span className="flex items-center gap-2"><Trophy className="size-6 text-amber-400" />{d.rank.tier}</span>}
                trend={all.length > 1 && latestPts.length > 1 ? { text: `${latestDelta >= 0 ? '+' : ''}${Math.round(latestDelta)} pts`, dir: latestDelta > 0 ? 'up' : latestDelta < 0 ? 'down' : 'flat' } : undefined}
                note={`${Math.round(d.rank.score)} pts · ${latestDelta >= 0 ? '+' : ''}${Math.round(latestDelta)} this season`} sub={`Peak ${d.rank.peak}`} />
            )}
            {d.top_heroes[0] && (
              <StatTile label="Most played" trend={{ text: `${d.top_heroes[0].mine.games} games`, dir: 'flat' }}
                value={<span className="flex items-center gap-2.5"><HeroFace hero={d.top_heroes[0]} size={36} />{d.top_heroes[0].name}</span>}
                note={`${pct(d.top_heroes[0].mine.rate)} win rate`} sub={d.top_heroes[0].role} />
            )}
            {d.facts.slice(0, 1).map((x) => <StatTile key={x.label} label={x.label} value={x.value} sub={x.sub} />)}
          </div>

          <Panel title="Recent form" hint="the last 30 games, newest on the right">
            <div className="flex flex-wrap items-center gap-8">
              <Gauge value={t.rate} label="win rate" />
              <FormStrip form={d.form} />
            </div>
          </Panel>

          {all.length > 1 ? (
            <Panel title="Rank journey" hint={pick === 'all' ? 'all seasons · pick one to zoom in' : `${points.length} games${start != null && end != null ? ` · ${end - start >= 0 ? '+' : ''}${Math.round(end - start)} pts over the season` : ''}`}
              action={
                <div className="flex items-center gap-2">
                  <ToggleGroup variant="outline" size="sm" className="hidden @3xl/main:flex" value={[String(pick === 'all' ? 'all' : pick === latest ? 'latest' : pick === prev ? 'prev' : '')]}
                    onValueChange={(v) => { const x = v[0]; if (x) setSeason(x === 'all' ? 'all' : x === 'latest' ? (latest ?? 'all') : (prev ?? 'all')) }}>
                    <ToggleGroupItem value="all">All seasons</ToggleGroupItem>
                    <ToggleGroupItem value="latest">Latest</ToggleGroupItem>
                    <ToggleGroupItem value="prev">Previous</ToggleGroupItem>
                  </ToggleGroup>
                  <Select value={String(pick)} onValueChange={(v) => setSeason(v === 'all' ? 'all' : Number(v))}>
                    <SelectTrigger size="sm" className="w-36"><SelectValue>{(v: string) => (v === 'all' ? 'All seasons' : (seasons.find((x) => String(x.season) === v)?.label ?? 'Season'))}</SelectValue></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All seasons</SelectItem>
                      {[...seasons].reverse().map((x) => <SelectItem key={x.season} value={String(x.season)}>{x.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              }>
              <div className="h-[340px]">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={points} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                    <defs>
                      <linearGradient id="rankfill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.45} /><stop offset="100%" stopColor="var(--primary)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="var(--border)" strokeOpacity={0.4} vertical={false} />
                    <XAxis dataKey="t" type="number" scale="time" domain={['dataMin', 'dataMax']} {...timeAxis(points[0].t, points[points.length - 1].t)} tick={AXIS} stroke="var(--border)" />
                    <YAxis domain={[lo - 40, hi + 40]} ticks={tierTicks.map((x) => x.floor)} interval={0} width={96}
                      tickFormatter={(v) => tierTicks.find((x) => x.floor === v)?.label.replace(pick === 'all' ? /\s3$/ : /$^/, '') ?? ''} tick={AXIS} stroke="var(--border)" />
                    {tierTicks.map((x) => <ReferenceLine key={x.level} y={x.floor} stroke="var(--muted-foreground)" strokeOpacity={0.22} />)}
                    {pick === 'all' && seasons.map((s) => <ReferenceLine key={s.season} x={s.t} stroke="var(--primary)" strokeDasharray="3 5" strokeOpacity={0.3} />)}
                    <Tooltip contentStyle={TIP} labelFormatter={(l) => date(Number(l))} formatter={(v, _n, item) => [`${Math.round(Number(v))} pts · ${(item.payload as { tier: string }).tier}`, 'Rank']} />
                    <Area dataKey="score" type="monotone" stroke="var(--primary)" strokeWidth={2} fill="url(#rankfill)" dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </Panel>
          ) : filters.mode === 1 ? <Panel title="Rank journey"><p className="text-sm text-muted-foreground">Rank is only tracked in ranked matches.</p></Panel> : null}

          <div className="grid gap-6 xl:grid-cols-[1.5fr_1fr]">
            <Panel title="Wins and losses by season" hint="decided games">
              <div className="h-[260px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={d.by_season} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
                    <CartesianGrid stroke="var(--border)" strokeOpacity={0.4} vertical={false} />
                    <XAxis dataKey="label" tick={AXIS} stroke="var(--border)" interval={0} angle={-35} textAnchor="end" height={56} />
                    <YAxis tick={AXIS} stroke="var(--border)" width={36} />
                    <Tooltip contentStyle={TIP} cursor={{ fill: 'var(--accent)', opacity: 0.4 }} formatter={(v, n) => [v, n === 'wins' ? 'Wins' : 'Losses']} />
                    <Legend formatter={(v) => (v === 'wins' ? 'Wins' : 'Losses')} wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="wins" stackId="a" fill={WIN} radius={[0, 0, 0, 0]} isAnimationActive={false} />
                    <Bar dataKey="losses" stackId="a" fill={LOSS} radius={[4, 4, 0, 0]} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Panel>
            <Panel title="Role split" hint="share of games"><RoleDonut roles={d.roles} /></Panel>
          </div>

          <div className="grid gap-6 xl:grid-cols-[1fr_1.2fr]">
            <Panel title="Top heroes" hint="by games">
              {d.top_heroes.map((h) => (
                <Link key={h.id} to={`/heroes/${h.id}?${query}`} className="flex items-center gap-3 border-b border-border/30 py-2 last:border-0 hover:bg-accent/40">
                  <HeroFace hero={h} size={38} />
                  <div className="min-w-0 flex-1"><div className="text-sm font-medium">{h.name}</div><Mastery games={h.career} /></div>
                  <span className="w-12 text-right text-sm tabular-nums text-muted-foreground">{h.mine.games}</span>
                  <WinBar s={h.mine} width={100} />
                </Link>
              ))}
            </Panel>
            <Panel title="Highlights" hint="what stands out in the match history"><Highlights facts={d.facts} /></Panel>
          </div>
        </>
      )}
    </Layout>
  )
}
