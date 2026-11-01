import { Sparkles } from 'lucide-react'
import { Panel, RangeRow, Spinner } from '@/components/bits'
import Layout from '@/components/Layout'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useApi, type PatternsData } from '@/lib/api'
import { pct, useFilters } from '@/lib/filters'
import { cn } from '@/lib/utils'

type Card = PatternsData['cards'][number]

function PatternCard({ c }: { c: Card }) {
  return (
    <div className={cn('min-w-0 rounded-xl border bg-card/60 p-4', c.clear ? 'border-primary/40' : 'border-border/60', c.id === 'season' && 'lg:col-span-2')}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <Tooltip>
          <TooltipTrigger className="text-sm font-semibold">{c.title}</TooltipTrigger>
          <TooltipContent>{c.note}</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger className={cn('flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium', c.clear ? 'bg-primary/20 text-primary' : 'bg-muted text-muted-foreground')}>
            {c.clear && <Sparkles className="size-3" />}{c.clear ? c.lead : 'no clear difference'}
          </TooltipTrigger>
          <TooltipContent>{c.detail}</TooltipContent>
        </Tooltip>
      </div>
      {c.buckets.map((b) => <RangeRow key={b.label} label={b.label} s={b} domain={[0.3, 0.7]} labelWidth={c.id === 'party' ? 170 : 128} />)}
      {c.caveat && c.clear && <p className="mt-2 text-xs text-muted-foreground">{c.caveat}</p>}
    </div>
  )
}

/** Weekday by time of day: every cell shows its win rate, with the number of games under it. */
function Heat({ heat }: { heat: NonNullable<PatternsData['heat']> }) {
  const cell = (d: number, b: number) => heat.cells.find((c) => c.d === d && c.b === b)
  const busiest = [...heat.cells].sort((a, b) => b.games - a.games)[0]
  return (
    <div>
      <div className="grid gap-1" style={{ gridTemplateColumns: `40px repeat(${heat.blocks.length}, 1fr)` }}>
        <div />{heat.blocks.map((b) => <div key={b} className="text-center text-[10px] text-muted-foreground">{b} h</div>)}
        {heat.days.map((day, d) => (
          <div key={day} className="contents">
            <div className="self-center text-xs text-muted-foreground">{day}</div>
            {heat.blocks.map((_, b) => {
              const c = cell(d, b)
              if (!c) return <div key={b} className="h-11 rounded-md bg-muted/20" />
              const dev = (c.rate ?? 0.5) - 0.5
              return (
                <Tooltip key={b}>
                  <TooltipTrigger className={cn('flex h-11 flex-col items-center justify-center rounded-md leading-none tabular-nums', !c.enough && 'opacity-55')}
                    style={{ background: c.rate != null ? `color-mix(in srgb, ${dev >= 0 ? '#10b981' : '#f97316'} ${c.enough ? Math.min(Math.max(Math.abs(dev) * 220, 14), 70) : 10}%, transparent)` : undefined }}>
                    <span className={cn('text-xs', c.enough && 'font-semibold')}>{c.rate != null ? `${Math.round(c.rate * 100)}%` : '–'}</span>
                    <span className="mt-0.5 text-[9px] text-muted-foreground">{c.games}</span>
                  </TooltipTrigger>
                  <TooltipContent>{day} {heat.blocks[b]} h: {c.games} games{c.enough ? ` · ${pct(c.rate)} win rate (${pct(c.lo)}–${pct(c.hi)})` : ' · under 5 decided games, too few to trust'}</TooltipContent>
                </Tooltip>
              )
            })}
          </div>
        ))}
      </div>
      {busiest && <p className="mt-3 text-xs text-muted-foreground">Busiest slot: <b className="text-foreground">{heat.days[busiest.d]} {heat.blocks[busiest.b]} h</b> with {busiest.games} games. Number under each rate = games.</p>}
    </div>
  )
}

/** One square per calendar day, 26 weeks: colour = win rate that day, strength = how many games were played. */
function Calendar({ days }: { days: NonNullable<PatternsData['days']> }) {
  const byDay = new Map(days.map((d) => [d.day, d]))
  const end = new Date(); end.setHours(0, 0, 0, 0)
  const start = new Date(end); start.setDate(start.getDate() - 7 * 26 + 1); start.setDate(start.getDate() - ((start.getDay() + 6) % 7))   // back to a Monday
  const weeks: { date: Date; key: string }[][] = []
  for (const d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
    const i = Math.floor((d.getTime() - start.getTime()) / 86400000 / 7)
    ;(weeks[i] ??= []).push({ date: new Date(d), key: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}` })
  }
  const max = Math.max(1, ...days.map((d) => d.games))
  return (
    <div className="overflow-x-auto">
      <div className="flex gap-1">
        <div className="flex flex-col gap-1 pr-1 pt-4 text-[10px] text-muted-foreground">{['Mon', '', 'Wed', '', 'Fri', '', 'Sun'].map((d, i) => <div key={i} className="h-4 leading-4">{d}</div>)}</div>
        {weeks.map((w, wi) => (
          <div key={wi} className="flex flex-col gap-1">
            <div className="h-3 text-[10px] leading-3 text-muted-foreground">{w[0].date.getDate() <= 7 ? w[0].date.toLocaleDateString(undefined, { month: 'short' }) : ''}</div>
            {w.map(({ date, key }) => {
              const d = byDay.get(key)
              const dev = d && d.wins + d.losses ? d.wins / (d.wins + d.losses) - 0.5 : 0
              return (
                <Tooltip key={key}>
                  <TooltipTrigger className="size-4 rounded-[3px] bg-muted/40"
                    style={d ? { background: `color-mix(in srgb, ${dev >= 0 ? '#10b981' : '#f97316'} ${20 + (d.games / max) * 65}%, transparent)` } : undefined} />
                  <TooltipContent>{date.toLocaleDateString(undefined, { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' })}: {d ? `${d.games} games · ${d.wins}W ${d.losses}L` : 'no games'}</TooltipContent>
                </Tooltip>
              )
            })}
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-3 text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1"><i className="size-3 rounded-[3px] bg-emerald-500/70" />more wins</span>
        <span className="flex items-center gap-1"><i className="size-3 rounded-[3px] bg-orange-500/70" />more losses</span>
        <span>stronger colour = more games that day</span>
      </div>
    </div>
  )
}

function SessionRow({ s }: { s: NonNullable<PatternsData['sessions']>[number] }) {
  const w = s.games.filter((g) => g.r === 'w').length, l = s.games.filter((g) => g.r === 'l').length
  const start = new Date(s.t * 1000), end = new Date(s.games[s.games.length - 1].t * 1000)
  const hm = (d: Date) => d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border/40 px-3 py-2">
      <div className="w-32 shrink-0">
        <div className="text-sm font-medium">{start.toLocaleDateString(undefined, { weekday: 'short', day: '2-digit', month: 'short' })}</div>
        <div className="text-[11px] text-muted-foreground">{hm(start)} – {hm(end)}</div>
      </div>
      <div className="flex flex-wrap gap-1">
        {s.games.map((g, i) => <span key={i} className={cn('size-3.5 rounded-full', g.r === 'w' ? 'bg-emerald-500' : g.r === 'l' ? 'border-2 border-orange-500' : 'bg-muted-foreground/50')} />)}
      </div>
      <div className="ml-auto shrink-0 text-right text-xs tabular-nums"><b className="text-emerald-400">{w}W</b> <b className="text-orange-400">{l}L</b><div className="text-muted-foreground">{s.games.length} {s.games.length === 1 ? 'game' : 'games'}</div></div>
    </div>
  )
}

export default function PatternsPage() {
  const { query } = useFilters()
  const { data: d, error } = useApi<PatternsData>('patterns', query)
  const clear = d?.cards.filter((c) => c.clear) ?? []
  const rest = d?.cards.filter((c) => !c.clear) ?? []
  return (
    <Layout title="Patterns">
      {error && <p className="text-sm text-destructive">Could not load: {error}</p>}
      {!d && !error && <Spinner />}
      {d && d.mode_n === 0 && <Panel title={`No ${d.mode_label} matches stored`}><p className="text-sm text-muted-foreground">Open Data to fetch them. A gentle fetch makes one request every 3 seconds, can take several hours, can be stopped and resumed, and stored matches are kept.</p></Panel>}
      {d && d.mode_n > 0 && d.cards.length === 0 && <Panel title="Patterns"><p className="text-sm text-muted-foreground">Not enough matches for this filter.</p></Panel>}
      {d && d.cards.length > 0 && (
        <>
          <Panel title="Stands out" hint={`${clear.length} of ${d.cards.length} splits differ after correcting for the number of checks · blue or orange only when the whole 95% range is on one side of 50%`}>
            {clear.length ? <div className="grid gap-4 lg:grid-cols-2">{clear.map((c) => <PatternCard key={c.id} c={c} />)}</div>
              : <p className="text-sm text-muted-foreground">Nothing clearly differs from a coin flip in this selection.</p>}
          </Panel>
          <Panel title="Activity" hint="every day of the last 26 weeks">{d.days && <Calendar days={d.days} />}</Panel>
          <div className="grid gap-6 xl:grid-cols-2">
            <Panel title="Games by weekday and time" hint="hover for the win rate range">{d.heat && <Heat heat={d.heat} />}</Panel>
            <Panel title="Latest sessions" hint="a gap of 1h30 starts a new session · ● win · ○ loss">
              <div className="flex flex-col gap-2">{(d.sessions ?? []).slice(0, 8).map((s) => <SessionRow key={s.t} s={s} />)}</div>
            </Panel>
          </div>
          {rest.length > 0 && (
            <details className="group">
              <summary className="cursor-pointer text-sm font-medium text-muted-foreground hover:text-foreground">
                No clear difference <span className="font-normal">· {rest.map((c) => c.title).join(', ')}</span>
              </summary>
              <div className="mt-4 grid gap-4 lg:grid-cols-2">{rest.map((c) => <PatternCard key={c.id} c={c} />)}</div>
            </details>
          )}
        </>
      )}
    </Layout>
  )
}
