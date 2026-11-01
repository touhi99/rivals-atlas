import { Cell, Pie, PieChart, PolarAngleAxis, RadialBar, RadialBarChart, ResponsiveContainer } from 'recharts'
import { cn } from '@/lib/utils'

export const WIN = '#10b981'
export const LOSS = '#f97316'
export const AXIS = { fontSize: 11, fill: 'var(--muted-foreground)' }
export const TIP = { background: 'var(--popover)', color: 'var(--popover-foreground)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }

/** A ring that fills to the win rate: blue above 50%, orange below. The number sits in the middle. */
export function Gauge({ value, label, size = 120 }: { value: number | null; label?: string; size?: number }) {
  const v = value == null ? 0 : value * 100
  const colour = value == null ? 'var(--muted)' : value >= 0.5 ? WIN : LOSS
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <ResponsiveContainer>
        <RadialBarChart innerRadius="78%" outerRadius="100%" data={[{ v }]} startAngle={90} endAngle={-270}>
          <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
          <RadialBar dataKey="v" cornerRadius={8} fill={colour} background={{ fill: 'var(--muted)' }} isAnimationActive={false} />
        </RadialBarChart>
      </ResponsiveContainer>
      <div className="absolute inset-0 grid place-items-center text-center">
        <div><div className="text-xl font-semibold tabular-nums">{value == null ? '–' : `${v.toFixed(0)}%`}</div>{label && <div className="text-[10px] text-muted-foreground">{label}</div>}</div>
      </div>
    </div>
  )
}

const ROLE_COLOR: Record<string, string> = { Vanguard: '#2dd4bf', Duelist: '#fb7185', Strategist: '#a3e635' }

export function RoleDonut({ roles }: { roles: { role: string; games: number }[] }) {
  const total = roles.reduce((a, r) => a + r.games, 0)
  return (
    <div className="flex items-center gap-6">
      <div className="relative size-36">
        <ResponsiveContainer>
          <PieChart>
            <Pie data={roles} dataKey="games" nameKey="role" innerRadius="62%" outerRadius="100%" paddingAngle={2} stroke="none" isAnimationActive={false}>
              {roles.map((r) => <Cell key={r.role} fill={ROLE_COLOR[r.role] ?? '#888'} />)}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="absolute inset-0 grid place-items-center text-center"><div><div className="text-lg font-semibold tabular-nums">{total}</div><div className="text-[10px] text-muted-foreground">games</div></div></div>
      </div>
      <div className="flex flex-col gap-2 text-sm">
        {roles.map((r) => (
          <div key={r.role} className="flex items-center gap-2">
            <span className="size-2.5 rounded-full" style={{ background: ROLE_COLOR[r.role] ?? '#888' }} />
            <span className="w-20">{r.role}</span>
            <span className="tabular-nums text-muted-foreground">{total ? Math.round((r.games / total) * 100) : 0}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/** The last games as a row of dots, newest on the right. */
export function FormStrip({ form }: { form: string[] }) {
  return (
    <div className="flex flex-wrap gap-1">
      {form.map((r, i) => (
        <span key={i} title={r} className={cn('grid size-5 place-items-center rounded-md text-[10px] font-semibold text-white', r === 'win' ? 'bg-emerald-500' : r === 'loss' ? 'bg-orange-500' : 'bg-muted-foreground/60')}>
          {r === 'win' ? 'W' : r === 'loss' ? 'L' : 'D'}
        </span>
      ))}
    </div>
  )
}

/** About six evenly spaced date ticks for a time axis, written short: "Oct 25" for a season, "Nov 2025" for a long range. */
export function timeAxis(min: number, max: number, count = 6) {
  const span = (max - min) / 86400
  const ticks = Array.from({ length: count }, (_, i) => Math.round(min + ((max - min) * i) / (count - 1)))
  const tickFormatter = (t: number) => new Date(t * 1000).toLocaleDateString(undefined, span > 200 ? { month: 'short', year: 'numeric' } : span > 20 ? { day: 'numeric', month: 'short' } : { day: 'numeric', month: 'short' })
  return { ticks, tickFormatter }
}
