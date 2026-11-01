import { Flame, Layers, Medal, Repeat, TrendingUp, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import type { OverviewData } from '@/lib/api'

type Fact = OverviewData['facts'][number]
const num = (f: Fact, k: string) => Number(f.data[k] ?? 0)

/** A thin ring that fills to a share of 100%. */
function Ring({ value, color, children, size = 72 }: { value: number; color: string; children?: ReactNode; size?: number }) {
  const r = 30, c = 2 * Math.PI * r
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg viewBox="0 0 72 72" className="size-full -rotate-90">
        <circle cx="36" cy="36" r={r} fill="none" stroke="var(--muted)" strokeWidth="7" />
        <circle cx="36" cy="36" r={r} fill="none" stroke={color} strokeWidth="7" strokeLinecap="round" strokeDasharray={`${Math.min(Math.max(value, 0), 1) * c} ${c}`} />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-sm font-semibold tabular-nums">{children}</div>
    </div>
  )
}

function Bar({ value, color, label, text }: { value: number; color: string; label: string; text: string }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-12 text-muted-foreground">{label}</span>
      <div className="h-2 flex-1 rounded-full bg-muted"><div className="h-full rounded-full" style={{ width: `${Math.min(Math.max(value, 0), 1) * 100}%`, background: color }} /></div>
      <b className="w-12 text-right tabular-nums">{text}</b>
    </div>
  )
}

function Card({ icon: Icon, tint, title, tag, children }: { icon: LucideIcon; tint: string; title: string; tag?: string; children: ReactNode }) {
  return (
    <div className="relative overflow-hidden rounded-xl border border-border/60 p-4" style={{ background: `linear-gradient(135deg, color-mix(in srgb, ${tint} 14%, transparent), transparent 60%)` }}>
      <div className="mb-3 flex items-center gap-3">
        <div className="grid size-9 place-items-center rounded-xl" style={{ background: `color-mix(in srgb, ${tint} 22%, transparent)`, color: tint }}><Icon className="size-5" /></div>
        <div className="text-sm font-medium">{title}</div>
        {tag && <span className="ml-auto rounded-full px-2 py-0.5 text-[10px] font-semibold" style={{ background: `color-mix(in srgb, ${tint} 22%, transparent)`, color: tint }}>{tag}</span>}
      </div>
      {children}
    </div>
  )
}

export default function Highlights({ facts }: { facts: Fact[] }) {
  const by = (k: string) => facts.find((f) => f.kind === k)
  const streak = by('streak'), points = by('points'), pool = by('pool'), medals = by('medals'), swaps = by('swaps')
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {streak && (() => {
        const w = num(streak, 'best_win'), l = num(streak, 'best_loss'), now = num(streak, 'now'), nowWin = streak.data.now_result === 'win'
        return (
          <Card icon={Flame} tint="#f59e0b" title="Streaks" tag={now >= 3 ? (nowWin ? 'On a roll' : 'Rough patch') : undefined}>
            <div className="flex items-end gap-6">
              <div><div className="text-3xl font-semibold leading-none tabular-nums text-emerald-400">{w}</div><div className="mt-1 text-[11px] text-muted-foreground">best win streak</div></div>
              <div><div className="text-3xl font-semibold leading-none tabular-nums text-orange-400">{l}</div><div className="mt-1 text-[11px] text-muted-foreground">worst loss streak</div></div>
            </div>
            <div className="mt-3 flex h-2 overflow-hidden rounded-full bg-muted"><div className="bg-emerald-500" style={{ width: `${(w / Math.max(w + l, 1)) * 100}%` }} /><div className="bg-orange-500 flex-1" /></div>
            <div className="mt-2 text-xs text-muted-foreground">Now: <b className={nowWin ? 'text-emerald-400' : 'text-orange-400'}>{now} {nowWin ? 'win' : 'loss'}{now === 1 ? '' : nowWin ? 's' : 'es'}</b> in a row</div>
          </Card>
        )
      })()}
      {points && (() => {
        const g = num(points, 'gain'), l = Math.abs(num(points, 'loss')), m = Math.max(g, l, 1)
        return (
          <Card icon={TrendingUp} tint="#10b981" title="Rank points" tag={g >= l ? 'Wins outweigh losses' : 'Losses outweigh wins'}>
            <div className="flex flex-col gap-2">
              <Bar value={g / m} color="#10b981" label="per win" text={`+${g.toFixed(1)}`} />
              <Bar value={l / m} color="#f97316" label="per loss" text={`−${l.toFixed(1)}`} />
            </div>
            <div className="mt-2 text-xs text-muted-foreground">average change in rank points</div>
          </Card>
        )
      })()}
      {pool && (() => {
        const t3 = num(pool, 'top3')
        return (
          <Card icon={Layers} tint="#2dd4bf" title="Hero pool" tag={t3 >= 0.7 ? 'Specialist' : t3 >= 0.5 ? 'Focused' : 'Flexible'}>
            <div className="flex items-center gap-4">
              <Ring value={t3} color="#2dd4bf">{Math.round(t3 * 100)}%</Ring>
              <div className="text-sm"><b className="text-xl tabular-nums">{num(pool, 'heroes')}</b> heroes played<div className="text-xs text-muted-foreground">the top 3 make up {Math.round(t3 * 100)}% of games</div></div>
            </div>
          </Card>
        )
      })()}
      {medals && (
        <Card icon={Medal} tint="#eab308" title="MVP and SVP">
          <div className="flex items-center gap-5">
            <div className="flex flex-col items-center"><div className="grid size-12 place-items-center rounded-full bg-amber-400/20 text-xl font-semibold tabular-nums text-amber-300 ring-2 ring-amber-400/50">{num(medals, 'mvp')}</div><div className="mt-1 text-[11px] text-muted-foreground">MVP · {Math.round(num(medals, 'mvp_share') * 100)}%</div></div>
            <div className="flex flex-col items-center"><div className="grid size-12 place-items-center rounded-full bg-slate-300/15 text-xl font-semibold tabular-nums text-slate-200 ring-2 ring-slate-300/40">{num(medals, 'svp')}</div><div className="mt-1 text-[11px] text-muted-foreground">SVP · {Math.round(num(medals, 'svp_share') * 100)}%</div></div>
            <div className="text-xs text-muted-foreground">best player of the winning side, and of the losing side</div>
          </div>
        </Card>
      )}
      {swaps && (() => {
        const s = num(swaps, 'share')
        return (
          <Card icon={Repeat} tint="#2dd4bf" title="Hero swaps" tag={s >= 0.5 ? 'Swaps often' : 'Sticks to one hero'}>
            <div className="flex items-center gap-4">
              <Ring value={s} color="#2dd4bf">{Math.round(s * 100)}%</Ring>
              <div className="text-xs text-muted-foreground">of matches use more than one hero</div>
            </div>
          </Card>
        )
      })()}
    </div>
  )
}
