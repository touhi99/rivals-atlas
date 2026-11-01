import { X } from 'lucide-react'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useApi, type Shell } from '@/lib/api'
import { useFilters } from '@/lib/filters'

const ANY = '__any'

function Pick({ value, onChange, placeholder, items }: {
  value: number | undefined; onChange: (v: number | undefined) => void; placeholder: string
  items: { id: number; label: string }[]
}) {
  return (
    <Select value={value === undefined ? ANY : String(value)} onValueChange={(v) => onChange(v === ANY ? undefined : Number(v))}>
      <SelectTrigger size="sm" className="w-[170px]">
        <SelectValue>{(v: string) => (v === ANY ? placeholder : (items.find((i) => String(i.id) === v)?.label ?? placeholder))}</SelectValue>
      </SelectTrigger>
      <SelectContent className="w-max min-w-(--anchor-width) max-w-[90vw]">
        <SelectItem value={ANY}>{placeholder}</SelectItem>
        {items.map((i) => <SelectItem key={i.id} value={String(i.id)}>{i.label}</SelectItem>)}
      </SelectContent>
    </Select>
  )
}

export default function FilterBar() {
  const { filters, query, set } = useFilters()
  // The choices depend only on the mode, so they are fetched with the mode alone.
  const { data: shell } = useApi<Shell>('shell', `mode=${filters.mode}`)
  const active = filters.season_from || filters.season_to || filters.hero || filters.map_id || filters.with.length
  const seasons = (shell?.seasons ?? []).map((s) => ({ id: s.id, label: s.label }))
  void query
  return (
    <div className="flex flex-wrap items-center gap-2">
      <ToggleGroup variant="outline" size="sm" value={[String(filters.mode)]}
        onValueChange={(v) => v[0] && set({ mode: Number(v[0]) })}>
        {(shell?.modes ?? [{ id: 2, label: 'ranked', matches: 0 }, { id: 1, label: 'quick play', matches: 0 }, { id: 0, label: 'all', matches: 0 }]).map((m) => (
          <ToggleGroupItem key={m.id} value={String(m.id)} className="px-3 capitalize aria-pressed:bg-primary aria-pressed:font-semibold aria-pressed:text-primary-foreground aria-pressed:hover:bg-primary">{m.label}</ToggleGroupItem>
        ))}
      </ToggleGroup>
      <Pick value={filters.season_from} onChange={(v) => set({ season_from: v })} placeholder="From season" items={seasons} />
      <Pick value={filters.season_to} onChange={(v) => set({ season_to: v })} placeholder="To season" items={seasons} />
      <Pick value={filters.hero} onChange={(v) => set({ hero: v })} placeholder="Any hero"
        items={(shell?.heroes ?? []).map((h) => ({ id: h.id, label: h.name }))} />
      <Pick value={filters.map_id} onChange={(v) => set({ map_id: v })} placeholder="Any map"
        items={(shell?.maps ?? []).map((m) => ({ id: m.id, label: m.name }))} />
      {active ? (
        <button type="button" className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
          onClick={() => set({ season_from: undefined, season_to: undefined, hero: undefined, map_id: undefined })}>
          <X className="size-3" /> Clear
        </button>
      ) : null}
    </div>
  )
}
