import { Loader2, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { HeroFace, MapBanner, Panel, RangeRow } from '@/components/bits'
import { Button } from '@/components/ui/button'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { cn } from '@/lib/utils'
import { postJson, useApi, type InsightRow, type InsightsData, type Observation } from '@/lib/api'

const when = (t: number) => new Date(t * 1000).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
const AGENTS: Record<string, string> = { coach: 'Coach', tilt_guard: 'Tilt guard', squad_synergy: 'Squad synergy', matchup_advisor: 'Matchup advisor' }
const TONE: Record<string, string> = {
  above_even: 'bg-emerald-500/15 text-emerald-300', above_site: 'bg-emerald-500/15 text-emerald-300',
  below_even: 'bg-orange-500/15 text-orange-300', below_site: 'bg-orange-500/15 text-orange-300',
  higher: 'bg-sky-500/15 text-sky-300', lower: 'bg-sky-500/15 text-sky-300', similar: 'bg-muted text-muted-foreground',
}

/** One piece of evidence as a range row: the dot is the win rate, the line is the 95% range, the centre mark is 50%. */
function Evidence({ r }: { r: InsightRow }) {
  const s = { rate: r.rate, lo: r.lo, hi: r.hi, n: r.n, enough: r.enough }
  const base = r.position != null ? `Game ${r.position >= 5 ? '5+' : r.position}` : (r.hero?.name ?? r.map?.name ?? 'Overall')
  const name = r.teammate ? `${r.teammate.present ? 'With' : 'Without'} a regular teammate${r.hero || r.map ? ` · ${base}` : ''}`
    : r.enemy ? `Against ${r.enemy.name}${r.hero ? ` · as ${r.hero.name}` : ''}` : base
  const scope = [r.mode, r.season ?? (r.earlier ? 'earlier seasons' : null)].filter(Boolean).join(' · ')
  return (
    <div className="flex items-center gap-3">
      {(r.enemy ?? r.hero) && <HeroFace hero={(r.enemy ?? r.hero)!} size={26} />}
      {r.map && <MapBanner map={{ place: r.map.name, icon: r.map.icon }} className="h-6 w-10 shrink-0" />}
      <div className="min-w-0 flex-1">
        <RangeRow label={<><span className="text-foreground">{name}</span> <span className="text-xs">{scope}</span></>} s={s} domain={[0.15, 0.85]} labelWidth={200} />
      </div>
    </div>
  )
}

function Card({ o }: { o: Observation }) {
  return (
    <div className="grid gap-5 rounded-xl border border-border/60 bg-card p-5 shadow-xs md:grid-cols-[1fr_1.15fr] md:items-center">
      <div className="flex flex-col items-start gap-2.5">
        <span className={cn('rounded-md px-2 py-0.5 text-[11px] font-medium', TONE[o.relation] ?? 'bg-muted text-muted-foreground')}>{o.badge}</span>
        <p className="text-base leading-snug font-medium">{o.text}</p>
        {o.agent && AGENTS[o.agent] && <span className="text-[11px] text-muted-foreground">{AGENTS[o.agent]}</span>}
      </div>
      <div className="flex flex-col">{o.evidence.map((r, i) => <Evidence key={i} r={r} />)}</div>
    </div>
  )
}

/** What the Coach, Tilt guard, Squad synergy and Matchup advisor found. Each card is the model's sentence with the numbers it rests on, checked by the app. */
export default function InsightsView() {
  const [tick, setTick] = useState(0)                      // changing it refetches
  const [mode, setMode] = useState(0)                      // 0 = ranked and quick play, 2 = ranked, 1 = quick play; each keeps its own saved result
  const { data: s } = useApi<InsightsData>('insights', `mode=${mode}&t=${tick}`)
  const busy = s?.job.state === 'running'                // one job at a time, whichever scope it is for
  const running = busy && (s.job.mode ?? 0) === mode
  useEffect(() => {
    if (!busy) return
    const t = window.setTimeout(() => setTick((n) => n + 1), 2000)
    return () => window.clearTimeout(t)
  }, [busy, tick])

  const run = async () => { await postJson(`/api/insights/run?mode=${mode}`, {}); setTick((n) => n + 1) }
  const d = s?.data && { ...s.data, observations: s.data.observations.filter((o) => o.relation !== 'similar') }   // older saved runs may still hold them

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ToggleGroup variant="outline" size="sm" value={[String(mode)]} onValueChange={(v) => v[0] && setMode(Number(v[0]))}>
          {[['0', 'All'], ['2', 'Ranked'], ['1', 'Quick play']].map(([id, label]) => (
            <ToggleGroupItem key={id} value={id} className="px-3 aria-pressed:bg-primary aria-pressed:font-semibold aria-pressed:text-primary-foreground aria-pressed:hover:bg-primary">{label}</ToggleGroupItem>
          ))}
        </ToggleGroup>
        <p className="text-sm text-muted-foreground">
          {d ? `${d.scope} · ${when(d.generated_at)} · ${d.model}${s?.stale ? ' · new matches since' : ''}` : 'What the agents find in the matches'}
        </p>
        <Button variant="outline" onClick={() => void run()} disabled={busy || !s}>
          {running ? <Loader2 className="animate-spin" /> : <RefreshCw />}{running ? 'Looking…' : d ? 'Refresh' : 'Run now'}
        </Button>
      </div>

      {s && !d && !running && (
        <Panel title="Nothing yet"><p className="text-sm text-muted-foreground">Run now sends questions to the model set for Ask, so it can use tokens. A small local model finds little; a stronger one works better. Without a model the rest of the app works as usual. After the first run, a fetch that finds new matches runs it again.</p></Panel>
      )}
      {s && !d && running && <Panel title="Looking"><p className="text-sm text-muted-foreground">The agents are going through the match history. This can take a minute.</p></Panel>}
      {d && !d.observations.length && <Panel title="Nothing stood out"><p className="text-sm text-muted-foreground">No observation passed the check this time. Small samples rarely show a clear difference; a stronger model may find more.</p></Panel>}

      {d && d.observations.length > 0 && (
        <>
          <div className="flex flex-col gap-4">{d.observations.map((o) => <Card key={o.text} o={o} />)}</div>
          <p className="text-[11px] text-muted-foreground">
            Written by the Coach, the Tilt guard, the Squad synergy agent and the Matchup advisor. The app runs the queries behind each sentence and checks that the difference is real, meaning the 95% ranges
            are apart. It cannot check the wording, so read the bars too.{d.dropped.length > 0 && ` ${d.dropped.length} suggested observation${d.dropped.length > 1 ? 's' : ''} did not pass.`}
          </p>
        </>
      )}
      {(s?.job.state === 'error' || d?.last_error) && <p className="text-xs text-destructive">Last run failed: {s?.job.error ?? d?.last_error}</p>}
    </div>
  )
}
