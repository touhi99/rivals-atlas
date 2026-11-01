import cytoscape from 'cytoscape'
import { Search } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { HeroFace } from '@/components/bits'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { GraphData, GraphEdge, GraphNode } from '@/lib/api'
import { cn } from '@/lib/utils'

const RELS: [string, string, string][] = [
  ['teammates', 'With', 'Own hero with teammates on the same team'],
  ['enemies', 'Against', 'Own hero against heroes on the other team'],
  ['maps', 'Maps', 'Heroes and the maps they were played on'],
  ['lobby', 'Lobby', 'Every player of every stored match, not only the player'],
]
const UP = [16, 185, 129], DOWN = [249, 115, 22], NEU = [142, 142, 147]
const mix = (a: number[], b: number[], t: number) => `rgb(${a.map((x, i) => Math.round(x + (b[i] - x) * t)).join(',')})`
const edgeColor = (r: number) => mix(NEU, r >= 0.5 ? UP : DOWN, Math.min(Math.abs(r - 0.5) * 3, 1))
const BLANK = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'
const short = (s: string) => s.replace(/ \(.*\)/, '')
const isClear = (n: GraphNode) => n.rate != null && n.n >= 15 && ((n.lo ?? 0) > 0.5 || (n.hi ?? 1) < 0.5)

function rings(all: GraphNode[]) {
  const heroes = all.filter((n) => n.kind !== 'map').sort((a, b) => Number(b.linked) - Number(a.linked) || b.games - a.games || a.name.localeCompare(b.name))
  const maps = all.filter((n) => n.kind === 'map').sort((a, b) => b.games - a.games)
  const pos: Record<number, { x: number; y: number }> = {}
  let i = 0, k = 0
  while (i < heroes.length) {
    const cap = k === 0 ? 1 : 6 * k
    for (let j = 0; j < cap && i < heroes.length; j++, i++) {
      const a = (2 * Math.PI * j) / cap - Math.PI / 2 + (k % 2 ? Math.PI / cap : 0)
      pos[heroes[i].id] = { x: k * 125 * Math.cos(a), y: k * 125 * Math.sin(a) }
    }
    k++
  }
  if (maps.length) {
    const R = (k + 0.9) * 125
    maps.forEach((m, j) => { const a = (2 * Math.PI * j) / maps.length - Math.PI / 2; pos[m.id] = { x: R * Math.cos(a), y: R * Math.sin(a) } })
  }
  return pos
}

type Row = { o: GraphNode; e: GraphEdge }

export default function ExploreGraph({ rel, setRel, minN, setMinN, data, games, loading }: {
  rel: string; setRel: (r: string) => void; minN: number; setMinN: (n: number) => void; data: GraphData | null; games: number; loading: boolean
}) {
  const host = useRef<HTMLDivElement>(null)
  const cy = useRef<cytoscape.Core | null>(null)
  const home = useRef<Record<number, { x: number; y: number }>>({})
  const [sel, setSel] = useState<number | null>(null)
  const [tip, setTip] = useState<{ x: number; y: number; html: string } | null>(null)
  const [all, setAll] = useState(false)
  const [find, setFind] = useState('')
  const [slider, setSlider] = useState(minN)
  const byId = useMemo(() => Object.fromEntries((data?.nodes ?? []).map((n) => [n.id, n])) as Record<number, GraphNode>, [data])
  useEffect(() => setSlider(minN), [minN])

  // (re)build the graph whenever the data changes
  useEffect(() => {
    if (!host.current || !data) return
    const pos = rings(data.nodes)
    home.current = pos
    const els: cytoscape.ElementDefinition[] = [
      ...data.nodes.map((n) => {
        const size = n.kind === 'map' ? 130 + Math.sqrt(n.games) * 5 : 30 + Math.sqrt(n.games) * 4
        return { data: { id: String(n.id), kind: n.kind, label: n.kind === 'map' ? n.name.replace(' · ', '\n') : short(n.name), icon: n.icon ?? BLANK, unlinked: !n.linked, size, h: n.kind === 'map' ? size * 0.5 : size, games: n.games,
          ring: isClear(n) ? ((n.hi ?? 1) < 0.5 ? '#f97316' : '#10b981') : '#6b7280' }, position: pos[n.id] }
      }),
      ...data.edges.map((e, i) => ({ data: { id: `e${i}`, source: String(e.source), target: String(e.target), w: Math.min(1 + e.n / 14, 6), color: edgeColor(e.rate), op: 0.25 + Math.min(Math.abs(e.rate - 0.5) * 2.4, 0.6), n: e.n, rate: e.rate, lo: e.lo, hi: e.hi } })),
    ]
    cy.current?.destroy()
    const c = cytoscape({
      container: host.current, elements: els, layout: { name: 'preset' }, wheelSensitivity: 0.25, minZoom: 0.25, maxZoom: 3.5,
      style: [
        { selector: 'node', style: { 'background-image': 'data(icon)', 'background-fit': 'cover', 'background-image-crossorigin': 'null', width: 'data(size)', height: 'data(size)', 'background-color': '#2a2a30', 'border-width': 3, 'border-color': 'data(ring)', label: 'data(label)', 'font-size': 14, 'font-weight': 600, color: '#c7c7cc', 'text-valign': 'bottom', 'text-margin-y': 4, 'text-wrap': 'wrap', 'text-max-width': 110, 'min-zoomed-font-size': 9, 'text-outline-width': 2, 'text-outline-color': '#141418' } as never },
        { selector: 'node[games = 0]', style: { opacity: 0.8, 'border-width': 1.5 } },
        { selector: 'node[?unlinked]', style: { opacity: 0.4, 'border-style': 'dashed' } },
        { selector: 'edge', style: { width: 'data(w)', 'line-color': 'data(color)', opacity: 0, 'curve-style': 'bezier' } as never },
        { selector: 'edge.all', style: { opacity: 'data(op)' } as never },
        { selector: 'edge.show', style: { opacity: 0.9 } },
        { selector: '.faded', style: { opacity: 0.12 } },
        { selector: 'node[kind = "map"]', style: { shape: 'round-rectangle', width: 'data(size)', height: 'data(h)', 'text-max-width': 150, 'font-size': 16 } as never },
        { selector: '.gone', style: { display: 'none' } },
        { selector: 'node:selected', style: { 'border-width': 4, 'border-color': '#34d399' } },
      ],
    })
    cy.current = c
    c.fit(undefined, 50)
    c.on('tap', 'node', (e) => setSel(Number(e.target.id())))
    c.on('tap', (e) => { if (e.target === c) setSel(null) })
    c.on('mouseover', 'node', (e) => {
      const n = byId[Number(e.target.id())] ?? data.nodes.find((x) => x.id === Number(e.target.id()))
      const p = e.renderedPosition
      if (n) setTip({ x: p.x + 14, y: p.y + 14, html: `<b>${n.name}</b><br>${n.games} games${n.rate != null ? ` · ${Math.round(n.rate * 100)}% wins` : ''}` })
      if (!cy.current?.$(':selected').length) e.target.connectedEdges().addClass('show')
    })
    c.on('mouseout', 'node', (e) => {
      if (!c.$(':selected').length) e.target.connectedEdges().removeClass('show')      // a focused hero keeps its lines
      setTip(null)
    })
    c.on('mouseover', 'edge', (e) => {
      const d = e.target.data(), a = data.nodes.find((x) => x.id === Number(e.target.source().id())), b = data.nodes.find((x) => x.id === Number(e.target.target().id()))
      const p = e.renderedPosition
      if (a && b) setTip({ x: p.x + 14, y: p.y + 14, html: `<b>${short(a.name)} ${rel === 'maps' ? 'on' : rel === 'enemies' ? 'vs' : '+'} ${short(b.name)}</b><br>${Math.round(d.rate * 100)}% in ${d.n} games (${Math.round(d.lo * 100)}–${Math.round(d.hi * 100)}%)` })
    })
    c.on('mouseout', 'edge', () => setTip(null))
    setSel((s) => (s != null && byId[s] ? s : null))
    return () => { c.destroy(); cy.current = null }
  }, [data]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { if (all) cy.current?.edges().addClass('all'); else cy.current?.edges().removeClass('all') }, [all, data])

  const rows: Row[] = useMemo(() => {
    if (sel == null || !data) return []
    let r = data.edges.filter((e) => e.source === sel).map((e) => ({ o: byId[e.target], e })).filter((x) => x.o && x.o.id !== sel)
    if (!r.length) r = data.edges.filter((e) => e.target === sel).map((e) => ({ o: byId[e.source], e })).filter((x) => x.o && x.o.id !== sel)
    return r
  }, [sel, data, byId])

  // focus layout: the chosen hero in the middle, partners around it from best to worst
  useEffect(() => {
    const c = cy.current
    if (!c || !data) return
    const restore = () => {
      c.batch(() => {
        c.elements().removeClass('gone faded show')
        c.nodes().forEach((n) => { const d = byId[Number(n.id())]; if (d) { n.position(home.current[d.id]); n.data('label', d.kind === 'map' ? d.name.replace(' · ', '\n') : short(d.name)) } })
      })
      c.$(':selected').unselect()
      c.resize(); c.fit(undefined, 50)
    }
    if (sel == null || !byId[sel]) { restore(); return }
    const node = c.getElementById(String(sel))
    if (!rows.length) { c.batch(() => { c.nodes().addClass('faded'); node.removeClass('faded') }); return }
    const ring = [...rows].sort((a, b) => b.e.rate - a.e.rate), k = ring.length, rad = Math.max(210, k * 15)
    c.batch(() => {
      c.elements().addClass('gone'); c.elements().removeClass('show faded')
      node.removeClass('gone'); node.position({ x: 0, y: 0 })
      ring.forEach((x, i) => {
        const m = c.getElementById(String(x.o.id)); m.removeClass('gone')
        const a = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(k, 1)
        m.position({ x: rad * Math.cos(a), y: rad * Math.sin(a) })
        m.data('label', `${short(x.o.name)}\n${Math.round(x.e.rate * 100)}% · ${x.e.n}`)
      })
      node.connectedEdges().removeClass('gone').addClass('show')
    })
    c.$(':selected').unselect(); node.select(); c.resize(); c.fit(c.elements().not('.gone'), 60)
  }, [sel, rows, data]) // eslint-disable-line react-hooks/exhaustive-deps

  const n = sel != null ? byId[sel] : null
  const best = rows.filter((x) => x.e.rate > 0.5).sort((a, b) => b.e.lo - a.e.lo).slice(0, 5)
  const worst = rows.filter((x) => x.e.rate <= 0.5).sort((a, b) => a.e.hi - b.e.hi).slice(0, 5)
  const lab = rel === 'maps' ? (n?.kind === 'map' ? ['Best heroes here', 'Worst heroes here'] : ['Best maps', 'Worst maps']) : rel === 'enemies' ? ['Beats', 'Loses to'] : ['Best with', 'Worst with']
  const empty = data && data.edges.length === 0

  const item = (x: Row) => (
    <button key={x.o.id} type="button" onClick={() => setSel(x.o.id)} className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left hover:bg-accent/50">
      <HeroFace hero={x.o} size={24} />
      <span className="flex-1 truncate text-sm">{x.o.kind === 'map' ? x.o.name : short(x.o.name)}</span>
      <b className={cn('text-sm tabular-nums', x.e.rate >= 0.5 ? 'text-emerald-400' : 'text-orange-400')}>{Math.round(x.e.rate * 100)}%</b>
      <small className="w-8 text-right text-xs text-muted-foreground">{x.e.n}</small>
    </button>
  )

  return (
    <div className={cn('relative h-[calc(100vh_-_290px)] min-h-[540px] overflow-hidden rounded-xl border border-border/60 bg-card/40', loading && 'opacity-70')}>
      <div className="absolute inset-y-0" style={{ left: n ? 262 : 0, right: n ? 290 : 0 }}><div ref={host} className="h-full w-full" /></div>
      {tip && <div className="pointer-events-none absolute z-20 rounded-md bg-foreground px-2.5 py-1.5 text-xs text-background" style={{ left: tip.x, top: tip.y }} dangerouslySetInnerHTML={{ __html: tip.html }} />}
      <div className="absolute left-4 top-4 z-10 flex w-[246px] flex-col gap-2.5 rounded-xl border border-border/60 bg-background/80 p-3 backdrop-blur">
        <div className="grid grid-cols-4 gap-1 rounded-lg bg-muted p-1">
          {RELS.map(([k, l, t]) => <button key={k} type="button" title={t} onClick={() => setRel(k)} className={cn('rounded-md py-1 text-xs font-medium', rel === k ? 'bg-background shadow' : 'text-muted-foreground hover:text-foreground')}>{l}</button>)}
        </div>
        <div className="relative">
          <Search className="absolute left-2 top-2 size-3.5 text-muted-foreground" />
          <Input list="gheroes" placeholder="Find a hero" value={find} className="h-8 pl-7" onChange={(e) => {
            setFind(e.target.value)
            const m = data?.nodes.find((x) => x.name.toLowerCase() === e.target.value.toLowerCase()); if (m) setSel(m.id)
          }} />
          <datalist id="gheroes">{(data?.nodes ?? []).map((x) => <option key={x.id} value={x.name} />)}</datalist>
        </div>
        <label className="flex items-center justify-between text-xs text-muted-foreground" title="A pair needs at least this many decided games"><span>Min games</span><b className="text-foreground">{slider}</b></label>
        <input type="range" min={1} max={80} value={slider} className="accent-[var(--primary)]" onChange={(e) => setSlider(Number(e.target.value))} onPointerUp={() => setMinN(slider)} onKeyUp={() => setMinN(slider)} />
        <div className="flex gap-3 text-[11px] text-muted-foreground"><span><i className="mr-1 inline-block h-[3px] w-3.5 bg-emerald-500 align-middle" />wins more</span><span><i className="mr-1 inline-block h-[3px] w-3.5 bg-orange-500 align-middle" />loses more</span></div>
        <label className="flex items-center justify-between text-xs text-muted-foreground"><span>Show all pairs</span><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /></label>
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{data ? `${data.nodes.filter((x) => x.linked).length} of ${data.nodes.length} linked · ${data.edges.length} pairs` : ''}</span>
          <Button size="xs" variant="outline" onClick={() => { setSel(null); cy.current?.fit(undefined, 50) }}>Reset view</Button>
        </div>
      </div>
      {n && (
        <div className="absolute right-4 top-4 z-10 max-h-[calc(100%_-_32px)] w-[270px] overflow-auto rounded-xl border border-border/60 bg-background/80 p-3 backdrop-blur">
          <button type="button" onClick={() => setSel(null)} className="mb-2 text-xs text-muted-foreground hover:text-foreground">‹ All heroes</button>
          <h3 className="flex items-center gap-2.5 text-[15px] font-semibold"><HeroFace hero={n} size={38} />{n.name}</h3>
          <div className="mt-2 text-sm text-muted-foreground">
            {n.rate != null ? <div className="flex justify-between"><span>{n.games} games {n.kind === 'map' ? 'on this map' : 'as this hero'}</span><b className={cn(isClear(n) ? ((n.hi ?? 1) < 0.5 ? 'text-orange-400' : 'text-emerald-400') : 'text-foreground')}>{Math.round(n.rate * 100)}%</b></div> : 'Not played by the player'}
          </div>
          {!rows.length && <p className="mt-3 text-sm text-muted-foreground">No pair with at least {minN} games.{minN > 3 && <> <button className="underline" onClick={() => setMinN(3)}>Use 3 games</button></>}</p>}
          {best.length > 0 && <><h4 className="mt-3 text-[11px] font-semibold uppercase text-muted-foreground">{lab[0]}</h4>{best.map(item)}</>}
          {worst.length > 0 && <><h4 className="mt-3 text-[11px] font-semibold uppercase text-muted-foreground">{lab[1]}</h4>{worst.map(item)}</>}
        </div>
      )}
      {empty && (
        <div className="absolute inset-0 z-[5] flex flex-col items-center justify-center gap-3 bg-background/85 px-10 text-center text-sm text-muted-foreground">
          <b className="text-foreground">No pairs to draw.</b>
          <span>{games} matches match these conditions, and no pair of heroes appears in {minN} or more of them.</span>
          {minN > 1 ? <Button size="sm" variant="outline" onClick={() => setMinN(1)}>Show every pair (1 game or more)</Button> : <span>Remove a condition (the chips above) to widen the selection.</span>}
        </div>
      )}
    </div>
  )
}
