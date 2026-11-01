import { Check, Users } from 'lucide-react'
import { Panel, Spinner, WinBar } from '@/components/bits'
import Layout from '@/components/Layout'
import { useApi, type SquadData } from '@/lib/api'
import { useFilters } from '@/lib/filters'
import { cn } from '@/lib/utils'

export default function SquadPage() {
  const { query, filters, setWith } = useFilters()
  const { data: d, error, loading } = useApi<SquadData>('squad', query)
  const toggle = (h: string) => setWith(filters.with.includes(h) ? filters.with.filter((x) => x !== h) : [...filters.with, h])
  return (
    <Layout title="Squad">
      {error && <p className="text-sm text-destructive">Could not load: {error}</p>}
      {!d && !error && <Spinner />}
      {d && (
        <div className={cn('flex flex-col gap-6', loading && 'opacity-60 transition-opacity')}>
          <Panel title="Party combinations" hint={d.cols.length ? `every combination of these ${d.cols.length} teammates that was played · click a row to filter everything to it${filters.with.length > d.max_party ? ` · showing the first ${d.max_party} picked` : ''}` : 'solo, duo, trio and bigger parties, and how each did'}>
            {d.cols.length === 0 ? (
              <div className="flex items-center gap-4 rounded-xl border border-dashed border-border/70 p-6 text-sm text-muted-foreground">
                <Users className="size-8 shrink-0 text-primary" />
                <div>
                  <div className="font-medium text-foreground">Pick teammates to compare</div>
                  <p className="mt-1">Choose two or more players in <b>Teammates</b> below. This table then lists every combination of them that was played together (alone, as a duo, as a trio and so on) with the games and win rate of each.</p>
                </div>
              </div>
            ) : (
            <table className="w-full text-sm">
              <thead className="text-xs text-muted-foreground">
                <tr className="border-b border-border/60">
                  <th className="py-2 text-left font-medium">Party</th>
                  {d.cols.map((c) => <th key={c.id} className="max-w-24 truncate px-2 text-center font-medium" title={c.name}>{c.name}</th>)}
                  <th className="text-right font-medium">Games</th><th className="pl-4 text-left font-medium">Win rate</th>
                </tr>
              </thead>
              <tbody>
                {d.combos.map((r) => (
                  <tr key={r.members.join()} onClick={() => setWith(r.members)} className="cursor-pointer border-b border-border/30 hover:bg-accent/40"
                    title={r.names.length ? `With ${r.names.join(' and ')}` : 'None of these teammates'}>
                    <td className="py-2 font-medium capitalize">{r.kind}</td>
                    {d.cols.map((c) => <td key={c.id} className="text-center"><span className={cn('inline-block size-3 rounded-full border-[1.5px]', r.members.includes(c.id) ? 'border-primary bg-primary' : 'border-muted-foreground/60')} /></td>)}
                    <td className="text-right tabular-nums">{r.n}</td>
                    <td className="pl-4"><WinBar s={r} width={100} /></td>
                  </tr>
                ))}
                {!d.combos.length && <tr><td colSpan={d.cols.length + 3} className="py-3 text-muted-foreground">No matches for this filter.</td></tr>}
              </tbody>
            </table>
            )}
          </Panel>
          <Panel title="Teammates" hint={`${d.regulars.length} regulars · pick up to ${d.max_party} to compare their combinations below; picking also keeps only the games with them on every page`} action={filters.with.length ? <button type="button" onClick={() => setWith([])} className="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline">Clear selection ({filters.with.length})</button> : undefined}>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {d.regulars.map((s) => {
                const on = filters.with.includes(s.id)
                return (
                  <button key={s.id} type="button" onClick={() => toggle(s.id)}
                    className={cn('rounded-xl border p-3 text-left transition', on ? 'border-primary bg-primary/10' : 'border-border/60 bg-background/40 hover:border-primary/50')}>
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex min-w-0 items-center gap-2.5">
                        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-primary/20 text-xs font-semibold text-primary">{s.name.slice(0, 2).toUpperCase()}</span>
                        <b className="truncate text-sm">{s.name}</b>
                      </div>
                      {on && <Check className="size-4 text-primary" />}
                    </div>
                    <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground"><span>{s.games} games together</span><WinBar s={s} width={60} /></div>
                  </button>
                )
              })}
              {!d.regulars.length && <p className="text-sm text-muted-foreground">No repeat teammates yet.</p>}
            </div>
          </Panel>
        </div>
      )}
    </Layout>
  )
}
