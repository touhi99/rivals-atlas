import { Link } from 'react-router-dom'
import { ArrowDown, ArrowUp, Flame, Snowflake } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from 'recharts'
import { HeroFace, Mastery, Panel, RoleChip, WinBar } from '@/components/bits'
import { AXIS, TIP, WIN } from '@/components/charts'
import Layout from '@/components/Layout'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useApi, type HeroesData, type HeroRow } from '@/lib/api'
import { pct, useFilters } from '@/lib/filters'
import { cn } from '@/lib/utils'

type Key = 'name' | 'games' | 'rate' | 'meta' | 'pick' | 'ban' | 'kda'
const val = (h: HeroRow, k: Key): number | string => {
  switch (k) {
    case 'name': return h.name
    case 'games': return h.mine?.games ?? 0
    case 'rate': return h.mine?.enough ? (h.mine.rate ?? -1) : -1
    case 'meta': return h.meta?.win ?? -1
    case 'pick': return h.meta?.pick ?? -1
    case 'ban': return h.meta?.ban ?? -1
    case 'kda': return h.mine?.enough ? (h.mine.kda ?? -1) : -1
  }
}

export default function HeroesPage() {
  const { query } = useFilters()
  const { data, error, loading } = useApi<HeroesData>('heroes', query)
  const [role, setRole] = useState('all')
  const [sort, setSort] = useState<{ k: Key; dir: 1 | -1 }>({ k: 'games', dir: -1 })
  const [all, setAll] = useState(false)

  const rows = useMemo(() => {
    const r = (data?.heroes ?? []).filter((h) => role === 'all' || h.role === role)
    r.sort((a, b) => {
      const x = val(a, sort.k), y = val(b, sort.k)
      return (typeof x === 'string' ? x.localeCompare(y as string) : (x as number) - (y as number)) * sort.dir
    })
    return r
  }, [data, role, sort])
  const shown = all ? rows : rows.slice(0, 15)
  const hasMeta = data?.meta_label != null
  const link = (id: number) => `/heroes/${id}?${query}`

  const th = (k: Key, label: string, tip?: string, right = true) => (
    <th className={cn('px-3 py-2 font-medium', right && 'text-right')}>
      <Tooltip>
        <TooltipTrigger className="inline-flex items-center gap-1 hover:text-foreground"
          onClick={() => setSort((s) => ({ k, dir: s.k === k ? (s.dir === 1 ? -1 : 1) : (k === 'name' ? 1 : -1) }))}>
          {label}
          {sort.k === k && (sort.dir === 1 ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />)}
        </TooltipTrigger>
        {tip && <TooltipContent>{tip}</TooltipContent>}
      </Tooltip>
    </th>
  )

  return (
    <Layout title="Heroes">
      {error && <p className="text-sm text-destructive">Could not load: {error}</p>}
      {!data && !error && <Skeleton className="h-96 w-full" />}
      {data && (
        <>
          {data.stands.findings.length > 0 && (
            <Panel title="Stands out" hint={`${data.stands.flagged} of ${data.stands.checked} checks · tested against all other games, corrected for the number of checks`}>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {data.stands.findings.map((f, i) => (
                  <div key={i} className={cn('flex items-center gap-3 rounded-lg border p-3',
                    f.direction === 'up' ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-orange-500/30 bg-orange-500/5')}>
                    {f.hero ? <HeroFace hero={f.hero} size={44} /> : (f.direction === 'up' ? <Flame className="size-8 text-emerald-400" /> : <Snowflake className="size-8 text-orange-400" />)}
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">{f.title}</div>
                      <div className="text-xs text-muted-foreground">
                        <b className={f.direction === 'up' ? 'text-emerald-400' : 'text-orange-400'}>{pct(f.rate)}</b> in {f.n} games vs {pct(f.base)} otherwise
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </Panel>
          )}
          {hasMeta && (
            <Panel title="Player against the meta" hint={`win rate on the ${Math.min(10, data.heroes.filter((h) => h.mine?.enough && h.meta?.win != null).length)} most played heroes · meta: ${data.meta_label}`}>
              <div className="h-[280px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.heroes.filter((h) => h.mine?.enough && h.meta?.win != null).slice(0, 10).map((h) => ({ name: h.name, tracked: +((h.mine!.rate ?? 0) * 100).toFixed(1), meta: h.meta!.win }))} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
                    <CartesianGrid stroke="var(--border)" strokeOpacity={0.4} vertical={false} />
                    <XAxis dataKey="name" tick={AXIS} stroke="var(--border)" interval={0} angle={-30} textAnchor="end" height={64} />
                    <YAxis domain={[30, 70]} tick={AXIS} stroke="var(--border)" width={36} unit="%" />
                    <ReferenceLine y={50} stroke="var(--muted-foreground)" strokeDasharray="4 4" />
                    <RTooltip contentStyle={TIP} cursor={{ fill: 'var(--accent)', opacity: 0.4 }} formatter={(v) => `${v}%`} />
                    <Legend wrapperStyle={{ fontSize: 12 }} formatter={(v) => (v === 'tracked' ? 'Player' : 'Meta')} />
                    <Bar dataKey="tracked" fill={WIN} radius={[4, 4, 0, 0]} isAnimationActive={false} />
                    <Bar dataKey="meta" fill="var(--muted-foreground)" fillOpacity={0.55} radius={[4, 4, 0, 0]} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Panel>
          )}
          <Panel title="Heroes" hint={`${data.heroes.filter((h) => h.mine).length} played of ${data.heroes.length}${hasMeta ? ` · meta: ${data.meta_label}` : ''}`}
            className={cn(loading && 'opacity-60 transition-opacity')}>
            <Tabs value={role} onValueChange={setRole} className="mb-3">
              <TabsList>
                {['all', 'Vanguard', 'Duelist', 'Strategist'].map((r) => <TabsTrigger key={r} value={r} className="capitalize">{r}</TabsTrigger>)}
              </TabsList>
            </Tabs>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs text-muted-foreground">
                  <tr className="border-b border-border/60">
                    {th('name', 'Hero', undefined, false)}
                    {th('games', 'Games', 'Games of the player on this hero')}
                    {th('rate', 'Win rate', 'Win rate of the player, decided games only')}
                    {hasMeta && th('meta', 'Meta win', `Win rate of everyone on this hero in ${data.meta_label}`)}
                    {hasMeta && th('pick', 'Pick', 'Share of matches where the hero was picked (everyone)')}
                    {hasMeta && th('ban', 'Ban', 'Share of matches where the hero was banned (everyone)')}
                    {th('kda', 'KDA', '(kills + assists) / deaths, from the player\'s own matches on this hero')}
                  </tr>
                </thead>
                <tbody>
                  {shown.map((h) => {
                    const m = h.mine
                    const d = m?.enough && m.rate != null && h.meta?.win != null ? m.rate * 100 - h.meta.win : null
                    const clear = m?.enough && h.meta?.win != null ? (m.lo * 100 > h.meta.win ? 'up' : m.hi * 100 < h.meta.win ? 'down' : null) : null
                    return (
                      <tr key={h.id} className={cn('border-b border-border/30 transition-colors hover:bg-accent/40', !m && 'opacity-50')}>
                        <td className="px-3 py-2">
                          <Link to={link(h.id)} className="flex items-center gap-3">
                            <HeroFace hero={h} />
                            <div>
                              <div className="font-medium">{h.name}</div>
                              <div className="mt-0.5 flex items-center gap-2"><RoleChip role={h.role} />{h.career > 0 && <Mastery games={h.career} />}</div>
                            </div>
                          </Link>
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">{m?.games ?? 0}</td>
                        <td className="px-3 py-2 text-right">{m ? <WinBar s={m} /> : <span className="text-muted-foreground">not played</span>}</td>
                        {hasMeta && (
                          <td className="px-3 py-2 text-right tabular-nums">
                            {h.meta?.win != null ? <>{h.meta.win.toFixed(1)}%
                              {d != null && <span className={cn('ml-1.5 text-xs', clear === 'up' ? 'text-emerald-400' : clear === 'down' ? 'text-orange-400' : 'text-muted-foreground')}>{d >= 0 ? '+' : ''}{d.toFixed(1)}</span>}</> : ''}
                          </td>
                        )}
                        {hasMeta && <td className="px-3 py-2 text-right tabular-nums">{h.meta?.pick != null ? `${h.meta.pick.toFixed(1)}%` : ''}</td>}
                        {hasMeta && <td className="px-3 py-2 text-right tabular-nums">{h.meta?.ban != null ? `${h.meta.ban.toFixed(1)}%` : ''}</td>}
                        <td className="px-3 py-2 text-right tabular-nums">{m?.kda != null ? m.kda.toFixed(2) : ''}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {rows.length > 15 && (
              <button type="button" onClick={() => setAll(!all)} className="mt-3 w-full rounded-lg bg-muted/60 py-2 text-xs text-muted-foreground hover:bg-muted">
                {all ? 'Show top 15' : `Show all ${rows.length} heroes`}
              </button>
            )}
            {!hasMeta && <p className="mt-3 text-xs text-muted-foreground">Pick, win and ban rates of everyone appear here after the next fetch from the Data page.</p>}
          </Panel>
        </>
      )}
    </Layout>
  )
}
