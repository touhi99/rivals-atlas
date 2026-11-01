import { ArrowLeft } from 'lucide-react'
import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer } from 'recharts'
import { AXIS } from '@/components/charts'
import { Link, useParams } from 'react-router-dom'
import { HeroFace, MapBanner, Panel, RangeRow, RoleChip, StatTile, Spinner, WinBar, Mastery } from '@/components/bits'
import Layout from '@/components/Layout'
import { useApi, type Edge, type HeroDetail } from '@/lib/api'
import { pct, useFilters } from '@/lib/filters'
import { cn } from '@/lib/utils'

const fmt = (x: number) => (x < 100 ? x.toFixed(1) : Math.round(x).toLocaleString())

function EdgeList({ title, edges }: { title: string; edges: Edge[] }) {
  const { query } = useFilters()
  if (!edges.length) return null
  return (
    <div>
      <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{title}</div>
      {edges.map((e) => (
        <Link key={e.id} to={`/heroes/${e.id}?${query}`} className="flex items-center gap-3 rounded-lg px-1 py-1.5 hover:bg-accent/40">
          <HeroFace hero={e} size={30} />
          <span className="flex-1 text-sm">{e.name}</span>
          <b className={cn('text-sm tabular-nums', e.rate >= 0.5 ? 'text-emerald-400' : 'text-orange-400')}>{pct(e.rate)}</b>
          <span className="w-8 text-right text-xs text-muted-foreground tabular-nums">{e.n}</span>
        </Link>
      ))}
    </div>
  )
}

export default function HeroDetailPage() {
  const { id } = useParams()
  const { query } = useFilters()
  const { data: d, error, loading } = useApi<HeroDetail>(`hero/${id}`, query)
  const m = d?.mine
  const mg = d?.meta?.group
  return (
    <Layout title={d?.hero.name ?? 'Hero'}>
      <Link to={{ pathname: '/heroes', search: query }} className="-mb-3 inline-flex w-fit items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-3" /> All heroes
      </Link>
      {error && <p className="text-sm text-destructive">Could not load: {error}</p>}
      {!d && !error && <Spinner />}
      {d && (
        <div className={cn('flex flex-col gap-6', loading && 'opacity-60 transition-opacity')}>
          <div className="flex items-center gap-5">
            <HeroFace hero={d.hero} size={84} />
            <div>
              <h2 className="text-2xl font-semibold tracking-tight">{d.hero.name}</h2>
              <div className="mt-1.5 flex items-center gap-3"><RoleChip role={d.hero.role} />{d.career > 0 && <Mastery games={d.career} />}</div>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            <StatTile label="Games" value={m?.games ?? 0} sub={m ? `${m.wins}W ${m.n - m.wins}L${m.draws ? ` ${m.draws}D` : ''}` : 'never played'} />
            <StatTile label="Win rate" value={m?.rate != null ? `${(m.rate * 100).toFixed(1)}%` : '–'}
              tone={m?.rate != null && m.lo > 0.5 ? 'up' : m?.rate != null && m.hi < 0.5 ? 'down' : undefined}
              sub={m ? `95% range ${pct(m.lo)}–${pct(m.hi)} · KDA ${m.kda?.toFixed(2) ?? '–'}` : undefined} />
            {mg && <StatTile label={`Meta win · ${d.meta_label}`} value={`${mg.win?.toFixed(1)}%`}
              sub={m?.enough && m.rate != null && mg.win != null ? `${m.rate * 100 - mg.win >= 0 ? '+' : ''}${(m.rate * 100 - mg.win).toFixed(1)} points for the player` : undefined} />}
            {mg && <StatTile label="Pick rate" value={`${mg.pick?.toFixed(1)}%`} sub={d.meta?.all?.pick != null ? `${d.meta.all.pick.toFixed(1)}% over all ranks` : undefined} />}
            {mg && <StatTile label="Ban rate" value={mg.ban != null ? `${mg.ban.toFixed(1)}%` : '–'} sub={d.meta?.all?.ban != null ? `${d.meta.all.ban.toFixed(1)}% over all ranks` : undefined} />}
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            {d.bench && d.bench.items.length > 0 && (
              <Panel title="Against other players on this hero" hint={`${d.bench.tracked_matches} matches of the player, ${d.bench.other_lines} of others`}>
                <table className="w-full text-sm">
                  <thead className="text-xs text-muted-foreground"><tr className="border-b border-border/60">
                    <th className="py-2 text-left font-medium">Per match</th><th className="text-right font-medium">Player</th><th className="text-right font-medium">Others</th><th className="pl-4 text-left font-medium">Better than</th></tr></thead>
                  <tbody>
                    {d.bench.items.map((i) => (
                      <tr key={i.metric} className="border-b border-border/30">
                        <td className="py-2 capitalize">{i.metric}</td>
                        <td className="text-right font-semibold tabular-nums">{fmt(i.tracked)}</td>
                        <td className="text-right text-muted-foreground tabular-nums">{fmt(i.others)}</td>
                        <td className="pl-4">
                          {i.beats_share == null ? <span className="text-xs text-muted-foreground">not ranked</span> : (
                            <div className="flex items-center gap-2">
                              <div className="h-1.5 w-24 rounded-full bg-muted"><div className="h-full rounded-full bg-primary" style={{ width: `${i.beats_share * 100}%` }} /></div>
                              <span className="text-xs tabular-nums">{Math.round(i.beats_share * 100)}%</span>
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="mt-2 h-[240px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <RadarChart data={d.bench.items.filter((i) => i.beats_share != null).map((i) => ({ metric: i.metric.replace('damage per 10 minutes', 'dmg / 10 min'), v: Math.round((i.beats_share ?? 0) * 100) }))} outerRadius="72%">
                      <PolarGrid stroke="var(--border)" />
                      <PolarAngleAxis dataKey="metric" tick={AXIS} />
                      <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                      <Radar dataKey="v" stroke="var(--primary)" fill="var(--primary)" fillOpacity={0.3} isAnimationActive={false} />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
                <p className="mt-1 text-center text-[11px] text-muted-foreground">share of other players' matches the player's average beats (50% is the middle)</p>
                <p className="mt-3 text-xs text-muted-foreground">
                  Win rate on this hero: player {pct(d.bench.rate)} ({d.bench.n} decided), other players {pct(d.bench.others_rate)}.
                  {!d.bench.enough && ' Few matches, so treat the comparison as a hint.'} Fewer deaths count as better.
                </p>
              </Panel>
            )}
            <Panel title="By season" hint="win rate with 95% interval">
              {d.seasons.length ? d.seasons.map((s) => <RangeRow key={s.label} label={s.label} s={s} />) : <p className="text-sm text-muted-foreground">No matches for this filter.</p>}
              <div className="mt-1 grid grid-cols-[110px_1fr_48px_40px] gap-3 text-[10px] text-muted-foreground"><span /><div className="flex justify-between"><span>0%</span><span>50%</span><span>100%</span></div></div>
            </Panel>
          </div>

          <Panel title="On maps">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {d.maps.map((x) => (
                <div key={x.id} className="flex items-center gap-3 rounded-lg border border-border/50 bg-background/40 p-2">
                  <MapBanner map={x} className="h-12 w-20 rounded-md" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">{x.place}</div>
                    <div className="text-[11px] text-muted-foreground">{x.mode} · {x.games} games</div>
                  </div>
                  <WinBar s={x} width={56} />
                </div>
              ))}
              {!d.maps.length && <p className="text-sm text-muted-foreground">No maps.</p>}
            </div>
          </Panel>

          <div className="grid gap-6 xl:grid-cols-2">
            <Panel title="With this hero" hint="teammates, the player's results">
              <EdgeList title="Best" edges={d.with.best} /><div className="h-3" /><EdgeList title="Worst" edges={d.with.worst} />
              {!d.with.best.length && !d.with.worst.length && <p className="text-sm text-muted-foreground">Not enough games with teammates yet.</p>}
            </Panel>
            <Panel title="Against" hint="enemy heroes, the player's results">
              <EdgeList title="Best" edges={d.against.best} /><div className="h-3" /><EdgeList title="Worst" edges={d.against.worst} />
              {!d.against.best.length && !d.against.worst.length && <p className="text-sm text-muted-foreground">Not enough games yet.</p>}
            </Panel>
          </div>

          {d.teamups.length > 0 && (
            <Panel title="Team-ups" hint="win rate of everyone, from the site's meta">
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {d.teamups.map((t, i) => (
                  <div key={i} className="flex items-center gap-3 rounded-lg border border-border/50 p-3">
                    <div className="flex -space-x-2">{t.heroes.map((h) => <HeroFace key={h.id} hero={h} size={34} />)}</div>
                    <div className="min-w-0 flex-1 truncate text-xs text-muted-foreground">{t.heroes.map((h) => h.name).join(' + ')}</div>
                    <div className="text-right"><b className={cn('text-sm tabular-nums', t.win >= 50 ? 'text-emerald-400' : 'text-orange-400')}>{t.win}%</b><div className="text-[10px] text-muted-foreground">{t.matches.toLocaleString()}</div></div>
                  </div>
                ))}
              </div>
            </Panel>
          )}

          {d.recent.length > 0 && (
            <Panel title="Latest matches">
              <table className="w-full text-sm">
                <thead className="text-xs text-muted-foreground"><tr className="border-b border-border/60">
                  <th className="py-2 text-left font-medium">Date</th><th className="text-left font-medium">Map</th><th className="text-left font-medium">Result</th>
                  <th className="text-right font-medium">K / D / A</th><th className="text-right font-medium">Points</th></tr></thead>
                <tbody>
                  {d.recent.map((r) => (
                    <tr key={r.played_at} className="border-b border-border/30">
                      <td className="py-2 text-muted-foreground">{new Date(r.played_at * 1000).toLocaleString(undefined, { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })}</td>
                      <td><span className="flex items-center gap-2">{r.map && <MapBanner map={r.map} className="h-5 w-8 rounded" />}{r.map?.name}</span></td>
                      <td className={cn('font-medium capitalize', r.result === 'win' ? 'text-emerald-400' : r.result === 'loss' ? 'text-orange-400' : 'text-muted-foreground')}>{r.result}</td>
                      <td className="text-right tabular-nums">{r.k} / {r.d} / {r.a}</td>
                      <td className={cn('text-right tabular-nums', (r.add_score ?? 0) > 0 ? 'text-emerald-400' : (r.add_score ?? 0) < 0 ? 'text-orange-400' : '')}>{r.add_score != null ? `${r.add_score > 0 ? '+' : ''}${Math.round(r.add_score)}` : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          )}
        </div>
      )}
    </Layout>
  )
}
