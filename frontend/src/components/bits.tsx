import { Minus, TrendingDown, TrendingUp } from 'lucide-react'
import type { ReactNode } from 'react'
import { Badge } from '@/components/ui/badge'
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { Hero, MapInfo, Stat } from '@/lib/api'
import { pct } from '@/lib/filters'
import { cn } from '@/lib/utils'

export const ROLE_STYLE: Record<string, string> = {
  Vanguard: 'bg-teal-500/15 text-teal-300 ring-teal-400/30',
  Duelist: 'bg-rose-500/15 text-rose-300 ring-rose-400/30',
  Strategist: 'bg-lime-500/15 text-lime-300 ring-lime-400/30',
}

export function RoleChip({ role }: { role: string }) {
  return <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-medium ring-1', ROLE_STYLE[role] ?? 'bg-muted text-muted-foreground ring-border')}>{role}</span>
}

export function HeroFace({ hero, size = 36 }: { hero: Pick<Hero, 'name' | 'icon'>; size?: number }) {
  return hero.icon ? (
    <img src={hero.icon} alt="" loading="lazy" width={size} height={size} style={{ width: size, height: size }}
      className="rounded-lg bg-muted object-cover ring-1 ring-border" />
  ) : (
    <div style={{ width: size, height: size }} className="grid place-items-center rounded-lg bg-muted text-xs font-semibold text-muted-foreground ring-1 ring-border">
      {hero.name.slice(0, 2)}
    </div>
  )
}

export function MapBanner({ map, className }: { map: Pick<MapInfo, 'place' | 'icon'>; className?: string }) {
  return map.icon ? (
    <img src={map.icon} alt="" loading="lazy" className={cn('object-cover', className)} />
  ) : (
    <div className={cn('grid place-items-center bg-gradient-to-br from-primary/30 to-muted text-[10px] font-semibold text-foreground/70', className)}>
      {map.place.split(' ').map((w) => w[0]).join('').slice(0, 3)}
    </div>
  )
}

/** Win rate as a bar around 50%: blue to the right when above, orange to the left when below. The thin range is the 95% interval. */
export function WinBar({ s, width = 120 }: { s: Stat; width?: number }) {
  if (!s.games) return <span className="text-muted-foreground">not played</span>
  const r = s.rate
  const up = r != null && r >= 0.5
  return (
    <Tooltip>
      <TooltipTrigger render={<div className="inline-flex items-center gap-2 tabular-nums" />}>
        <>
          <div className="relative h-2 rounded-full bg-muted" style={{ width }}>
            <div className="absolute inset-y-0 left-1/2 w-px bg-foreground/30" />
            {r != null && s.enough && (
              <div className={cn('absolute inset-y-0 rounded-full', up ? 'bg-emerald-500' : 'bg-orange-500')}
                style={{ left: `${Math.min(r, 0.5) * 100}%`, width: `${Math.abs(r - 0.5) * 100}%` }} />
            )}
            {r != null && !s.enough && <div className="absolute inset-y-0 rounded-full bg-muted-foreground/40" style={{ left: `${r * 100 - 1}%`, width: 2 }} />}
          </div>
          <span className={cn('w-10 text-right text-sm font-medium', !s.enough && 'text-muted-foreground')}>{pct(r)}</span>
        </>
      </TooltipTrigger>
      <TooltipContent>
        {s.wins} wins in {s.n} decided games{s.enough ? ` · 95% range ${pct(s.lo)}–${pct(s.hi)}` : ' · too few games to trust'}
      </TooltipContent>
    </Tooltip>
  )
}

/** Mastery pips from games played: a light touch of progression, not a score. */
export const LEVELS = [5, 15, 40, 100, 250]
export function Mastery({ games }: { games: number }) {
  const lvl = LEVELS.filter((t) => games >= t).length
  const next = LEVELS[lvl]
  return (
    <Tooltip>
      <TooltipTrigger render={<div className="inline-flex items-center gap-1" />}>
        <>
          {LEVELS.map((t, i) => (
            <span key={t} className={cn('size-2 rotate-45 rounded-[2px]', i < lvl ? 'bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,.6)]' : 'bg-muted')} />
          ))}
        </>
      </TooltipTrigger>
      <TooltipContent>{games} games in all modes and seasons · mastery {lvl}/{LEVELS.length}{next ? ` · ${next - games} more for the next` : ' · maxed'}</TooltipContent>
    </Tooltip>
  )
}

export function Panel({ title, hint, action, children, className }: { title: string; hint?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <Card className={cn('shadow-xs', className)}>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        {hint && <CardDescription>{hint}</CardDescription>}
        {action && <CardAction>{action}</CardAction>}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

export function StatTile({ label, value, sub, tone, trend, note, children }: {
  label: string; value?: ReactNode; sub?: ReactNode; tone?: 'up' | 'down'; trend?: { text: string; dir: 'up' | 'down' | 'flat' }; note?: ReactNode; children?: ReactNode
}) {
  return (
    <Card className="@container/card bg-gradient-to-t from-primary/5 to-card shadow-xs">
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className={cn('text-2xl font-semibold tabular-nums whitespace-nowrap', tone === 'up' && 'text-emerald-400', tone === 'down' && 'text-orange-400')}>{value}{children}</CardTitle>
        {trend && (
          <CardAction>
            <Badge variant="outline" className={cn(trend.dir === 'up' && 'text-emerald-400', trend.dir === 'down' && 'text-orange-400')}>
              {trend.dir === 'up' ? <TrendingUp /> : trend.dir === 'down' ? <TrendingDown /> : <Minus />}{trend.text}
            </Badge>
          </CardAction>
        )}
      </CardHeader>
      {(sub || note) && (
        <CardFooter className="flex-col items-start gap-1 text-sm">
          {note && <div className="line-clamp-1 font-medium">{note}</div>}
          {sub && <div className="text-muted-foreground">{sub}</div>}
        </CardFooter>
      )}
    </Card>
  )
}

export function Spinner({ lines = 6 }: { lines?: number }) {
  return <div className="flex flex-col gap-3">{Array.from({ length: lines }, (_, i) => <div key={i} className="h-10 animate-pulse rounded-lg bg-muted/50" />)}</div>
}

/** One row of a range chart: the dot is the observed rate, the line is the 95% interval, the centre mark is 50%. */
export function RangeRow({ label, s, domain = [0, 1], labelWidth = 110 }: {
  label: ReactNode; s: { rate: number | null; lo: number; hi: number; n: number; enough: boolean }; domain?: [number, number]; labelWidth?: number
}) {
  const [a, b] = domain
  const at = (x: number) => `${Math.min(Math.max((x - a) / (b - a), 0), 1) * 100}%`
  const r = s.rate
  return (
    <div className="grid grid-cols-[var(--lw)_1fr_48px_40px] items-center gap-3 py-1.5 text-sm" style={{ ['--lw' as string]: `${labelWidth}px` }}>
      <div className="truncate text-muted-foreground">{label}</div>
      <div className="relative h-4">
        <div className="absolute inset-y-0 w-px bg-foreground/25" style={{ left: at(0.5) }} />
        <div className="absolute top-1/2 h-px -translate-y-1/2 bg-muted-foreground/60" style={{ left: at(s.lo), width: `${(Math.min(Math.max(s.hi, a), b) - Math.min(Math.max(s.lo, a), b)) / (b - a) * 100}%` }} />
        {r != null && <div className={cn('absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full', !s.enough ? 'bg-muted-foreground' : r >= 0.5 ? 'bg-emerald-500' : 'bg-orange-500')} style={{ left: at(r) }} />}
      </div>
      <div className="text-right font-medium tabular-nums">{pct(r)}</div>
      <div className="text-right text-xs text-muted-foreground tabular-nums">{s.n}</div>
    </div>
  )
}

