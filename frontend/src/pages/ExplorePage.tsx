import { X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from 'recharts'
import { timeAxis } from '@/components/charts'
import ExploreGraph from '@/components/ExploreGraph'
import { HeroFace, MapBanner, Panel, Spinner, WinBar } from '@/components/bits'
import Layout from '@/components/Layout'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { getJson, useApi, type ExploreData, type GraphData, type Opt, type Tally } from '@/lib/api'
import { pct } from '@/lib/filters'
import { cn } from '@/lib/utils'

const ANY = '__any'
const LIST_KEYS = ['banned', 'not_banned']
const MAX_PICK = 3
const SPEC_KEYS = ['mode', 'season_from', 'season_to', 'map_id', 'hero', 'role', 'block', 'weekday', 'session_pos', 'regulars', 'group_by']

function Field({ label, value, onChange, options, any = 'Any' }: { label: string; value: string; onChange: (v: string) => void; options: Opt[]; any?: string }) {
  return (
    <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">
      {label}
      <Select value={value || ANY} onValueChange={(v) => onChange(v === ANY ? '' : String(v))}>
        <SelectTrigger size="sm" className="w-full">
          <SelectValue>{(v: string) => (v === ANY ? any : (options.find((o) => String(o.value) === v)?.label ?? any))}</SelectValue>
        </SelectTrigger>
        <SelectContent className="w-max min-w-(--anchor-width) max-w-[90vw]">
          <SelectItem value={ANY}>{any}</SelectItem>
          {options.map((o) => <SelectItem key={o.value} value={String(o.value)}>{o.label}</SelectItem>)}
        </SelectContent>
      </Select>
    </label>
  )
}

function MultiField({ label, values, onChange, options, hint }: { label: string; values: string[]; onChange: (v: string[]) => void; options: Opt[]; hint: string }) {
  return (
    <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">
      {label} <span className="text-[10px] opacity-70">(up to {MAX_PICK}, {hint})</span>
      <Select multiple value={values} onValueChange={(v) => onChange((v as string[]).slice(-MAX_PICK))}>
        <SelectTrigger size="sm" className="w-full">
          <SelectValue>{(v: string[]) => (v.length ? v.map((x) => options.find((o) => String(o.value) === x)?.label ?? x).join(', ') : 'Any')}</SelectValue>
        </SelectTrigger>
        <SelectContent className="w-max min-w-(--anchor-width) max-w-[90vw]">
          {options.map((o) => <SelectItem key={o.value} value={String(o.value)}>{o.label}</SelectItem>)}
        </SelectContent>
      </Select>
    </label>
  )
}

function Rows({ rows, icon }: { rows: (Tally & { icon?: string | null })[]; icon?: 'map' }) {
  return (
    <div>
      {rows.map((g) => (
        <div key={g.label} className={cn('grid grid-cols-[minmax(120px,1fr)_40px_auto] items-center gap-3 border-b border-border/30 py-1.5 last:border-0', !g.enough && 'opacity-55')}>
          <span className="flex min-w-0 items-center gap-2 text-sm">
            {icon === 'map' && <MapBanner map={{ place: g.label, icon: g.icon ?? null }} className="h-6 w-14 shrink-0 rounded" />}
            <span className="truncate">{g.label}</span>
          </span>
          <span className="text-right text-xs text-muted-foreground tabular-nums">{g.n}</span>
          <WinBar s={{ ...g, games: g.games, draws: 0, kda: null }} width={110} />
        </div>
      ))}
    </div>
  )
}

export default function ExplorePage() {
  const [params, setParams] = useSearchParams()
  const view = params.get('view') === 'breakdown' ? 'breakdown' : 'graph'
  const rel = ['teammates', 'enemies', 'lobby', 'maps'].includes(params.get('rel') ?? '') ? params.get('rel')! : 'teammates'
  const specQuery = useMemo(() => {
    const q = new URLSearchParams()
    for (const k of [...SPEC_KEYS, 'go']) { const v = params.get(k); if (v) q.set(k, v) }
    for (const k of LIST_KEYS) params.getAll(k).forEach((v) => q.append(k, v))
    return q.toString()
  }, [params])
  const { data: d, error, loading } = useApi<ExploreData>('explore', specQuery)
  const minParam = Number(params.get('min_n')) || 0
  const minN = minParam || d?.default_min || 15
  const graphQuery = `${specQuery}&rel=${rel}&min_n=${minN}`
  const [graph, setGraph] = useState<{ key: string; data: GraphData | null }>({ key: '', data: null })
  useEffect(() => {
    if (view !== 'graph' || !d?.result) return
    let live = true
    getJson<GraphData>(`/api/map?${graphQuery}`).then((g) => live && setGraph({ key: graphQuery, data: g })).catch(() => live && setGraph({ key: graphQuery, data: null }))
    return () => { live = false }
  }, [graphQuery, view, d?.result?.games]) // eslint-disable-line react-hooks/exhaustive-deps

  const patch = (p: Record<string, string>) => setParams((prev) => {
    const n = new URLSearchParams(prev)
    for (const [k, v] of Object.entries(p)) { if (v) n.set(k, v); else n.delete(k) }
    n.set('go', '1'); n.delete('focus')
    return n
  })
  const list = (k: string) => params.getAll(k)
  const patchList = (k: string, values: string[]) => setParams((prev) => {
    const n = new URLSearchParams(prev)
    n.delete(k); values.forEach((v) => n.append(k, v)); n.set('go', '1'); n.delete('focus')
    return n
  })
  const dropChip = (drop: string) => setParams(() => { const n = new URLSearchParams(drop); if (view === 'breakdown') n.set('view', 'breakdown'); return n })
  const r = d?.result
  const spec = d?.spec ?? {}
  const val = (k: string) => (spec[k] !== undefined ? String(spec[k]) : (params.get(k) ?? ''))
  const c = d?.choices
  const P = r?.panels

  return (
    <Layout title="Explore">
      {error && <p className="text-sm text-destructive">Could not load: {error}</p>}
      {!d && !error && <Spinner />}
      {d && c && (
        <div className={cn('flex flex-col gap-5', loading && 'opacity-70 transition-opacity')}>
          <div className="flex flex-wrap items-center gap-2">
            {d.chips.map((chip) => (
              <button key={chip.label} type="button" onClick={() => dropChip(chip.drop)} title="Remove this condition"
                className="inline-flex items-center gap-1 rounded-full bg-primary/15 px-3 py-1 text-xs font-medium text-primary ring-1 ring-primary/30 hover:bg-primary/25">
                {chip.label}<X className="size-3" />
              </button>
            ))}
            {!d.chips.length && <span className="text-sm text-muted-foreground">No conditions: every {val('mode') === '1' ? 'quick play ' : val('mode') === '0' ? '' : 'ranked '}match.</span>}
          </div>

          <Panel title="More filters" hint="added to the filters at the top · changes apply straight away">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Field label="Role played" value={val('role')} onChange={(v) => patch({ role: v })} options={c.roles} />
              <MultiField label="Heroes banned" values={list('banned')} onChange={(v) => patchList('banned', v)} options={c.heroes} hint="all of them" />
              <MultiField label="Heroes not banned" values={list('not_banned')} onChange={(v) => patchList('not_banned', v)} options={c.heroes} hint="none of them" />
              <Field label="Time of day" value={val('block')} onChange={(v) => patch({ block: v })} options={c.blocks} />
              <Field label="Weekday" value={val('weekday')} onChange={(v) => patch({ weekday: v })} options={c.weekdays} />
              <Field label="Game in session" value={val('session_pos')} onChange={(v) => patch({ session_pos: v })} options={c.positions} />
              <Field label="Regular teammates" value={val('regulars')} onChange={(v) => patch({ regulars: v })} options={c.regulars} />
              <Field label="Break down by" value={d.group_by ?? ''} onChange={(v) => { patch({ group_by: v }); if (v) setParams((p) => { const n = new URLSearchParams(p); n.set('view', 'breakdown'); return n }) }} options={c.groups} any="Nothing" />
            </div>
          </Panel>

          {d.error && <Panel title="Could not run this"><p className="text-sm text-muted-foreground">{d.error}</p></Panel>}
          {r && !d.error && (
            <>
              <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
                {r.total.n ? (
                  <>
                    <div className="text-3xl font-semibold tracking-tight tabular-nums">{r.total.wins}<small className="ml-1.5 text-sm font-normal text-muted-foreground">wins in {r.total.n} decided games</small></div>
                    <WinBar s={{ ...r.total, games: r.games, draws: r.draws, kda: null }} width={180} />
                    {!r.total.enough && <span className="text-sm text-muted-foreground">Too few games to say anything (at least 5).</span>}
                  </>
                ) : <span className="text-sm text-muted-foreground">No decided matches satisfy these conditions.</span>}
                <span className="text-sm text-muted-foreground">{r.games} matches{r.draws ? `, ${r.draws} draw${r.draws !== 1 ? 's' : ''} not counted` : ''}</span>
              </div>
              <Tabs value={view} onValueChange={(v) => setParams((p) => { const n = new URLSearchParams(p); n.set('view', String(v)); return n })}>
                <TabsList><TabsTrigger value="graph">Graph</TabsTrigger><TabsTrigger value="breakdown">Breakdown</TabsTrigger></TabsList>
              </Tabs>
              {d.graph_stale && <Panel title="The graph file is behind the database"><p className="text-sm text-muted-foreground">Matches or seasons were added after it was built, so some numbers here are out of date. Rebuild it with <code>uv run rivals-atlas graph --ladybug</code>.</p></Panel>}

              {view === 'graph' && (
                <>
                  <p className="-mb-2 text-xs text-muted-foreground">Each circle is a hero, bigger means more games. Click one to see which heroes it wins and loses with (or against, or on which maps). Green ring: wins more than half, orange: loses more.</p>
                  <ExploreGraph rel={rel} setRel={(x) => setParams((p) => { const n = new URLSearchParams(p); n.set('rel', x); return n })}
                    minN={minN} setMinN={(n) => setParams((p) => { const q = new URLSearchParams(p); q.set('min_n', String(n)); return q })}
                    data={graph.data} games={r.games} loading={graph.key !== graphQuery} />
                </>
              )}

              {view === 'breakdown' && P && (
                <div className="flex flex-col gap-6">
                  {r.groups.length > 0 && <Panel title={r.group_title || 'Breakdown'}><Rows rows={r.groups} /></Panel>}
                  <Panel title="Heroes" hint="portrait, games played, win rate with its uncertainty">
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                      {P.heroes.slice(0, 18).map((h) => (
                        <button key={h.id} type="button" onClick={() => patch({ hero: String(h.id) })} title="Only this hero"
                          className={cn('flex flex-col items-start gap-1 rounded-xl border border-border/60 bg-background/40 p-3 text-left hover:border-primary/60', !h.enough && 'opacity-60')}>
                          <HeroFace hero={{ name: h.label, icon: h.icon }} size={44} />
                          <b className="text-sm">{h.label}</b>
                          <span className="text-xs text-muted-foreground">{h.games} games</span>
                          <WinBar s={{ ...h, draws: 0, kda: null }} width={90} />
                        </button>
                      ))}
                    </div>
                  </Panel>
                  <Panel title="Win rate by week" hint="weeks with at least 8 decided games; the middle line is 50%">
                    {P.trend ? (
                      <div className="h-[200px]">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={P.trend.points} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                            <CartesianGrid stroke="var(--border)" strokeOpacity={0.4} vertical={false} />
                            <XAxis dataKey="week" type="number" scale="time" domain={['dataMin', 'dataMax']} {...timeAxis(P.trend.points[0].week, P.trend.points[P.trend.points.length - 1].week)} tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }} stroke="var(--border)" />
                            <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }} stroke="var(--border)" width={36} unit="%" />
                            <ReferenceLine y={50} stroke="var(--muted-foreground)" strokeDasharray="4 4" />
                            <RTooltip contentStyle={{ background: 'var(--popover)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }}
                              labelFormatter={(t) => new Date(Number(t) * 1000).toLocaleDateString()} formatter={(v, _n, i) => [`${v}% in ${(i.payload as { n: number }).n} games`, 'Win rate']} />
                            <Line dataKey="rate" stroke="var(--primary)" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    ) : <p className="text-sm text-muted-foreground">Not enough weeks with data to draw a trend.</p>}
                  </Panel>
                  <div className="grid gap-6 xl:grid-cols-2">
                    <Panel title="Maps" hint="most played first">{P.maps.length ? <Rows rows={P.maps.slice(0, 10)} icon="map" /> : <p className="text-sm text-muted-foreground">No map data for these matches.</p>}</Panel>
                    <Panel title="When" hint="win rate by weekday and time of day; blank cells have fewer than 5 games">
                      <div className="grid gap-1" style={{ gridTemplateColumns: `44px repeat(${P.blocks.length}, 1fr)` }}>
                        <div />{P.blocks.map((b) => <div key={b} className="text-center text-[10px] text-muted-foreground">{b.split(' ')[0]}</div>)}
                        {P.heat.map((row, di) => (
                          <div key={di} className="contents">
                            <div className="self-center text-xs text-muted-foreground">{P.weekdays[di]}</div>
                            {row.map((cell, bi) => {
                              const dev = (cell.rate ?? 0.5) - 0.5
                              return (
                                <Tooltip key={bi}>
                                  <TooltipTrigger className="grid h-9 place-items-center rounded-md bg-muted/40 text-xs font-semibold tabular-nums"
                                    style={cell.enough ? { background: `color-mix(in srgb, ${dev >= 0 ? '#10b981' : '#f97316'} ${Math.min(Math.max(Math.abs(dev) * 300, 14), 75)}%, transparent)` } : { opacity: 0.4 }}>
                                    {cell.enough ? Math.round((cell.rate ?? 0) * 100) : ''}
                                  </TooltipTrigger>
                                  <TooltipContent>{P.weekdays[di]} {P.blocks[bi]}: {cell.wins} wins in {cell.n} decided games{cell.enough ? ` (${pct(cell.rate)})` : ' (too few to show)'}</TooltipContent>
                                </Tooltip>
                              )
                            })}
                          </div>
                        ))}
                      </div>
                    </Panel>
                    <Panel title="Roles"><Rows rows={P.roles} /></Panel>
                    <Panel title="Seasons">{P.seasons.length ? <Rows rows={P.seasons.slice(0, 8)} /> : <p className="text-sm text-muted-foreground">No season data.</p>}</Panel>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </Layout>
  )
}
