import { ArrowUp, Check, ChevronRight, Database, Loader2, Plus, Sparkles, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { MapBanner } from '@/components/bits'
import { Chip, Rich, useEntities } from '@/components/Entities'
import { getJson, postJson, useApi, type AskCall, type AskInfo, type AskJob, type Shell } from '@/lib/api'
import { cn } from '@/lib/utils'

type Turn = { id: string; question: string; job: AskJob | null; error?: string }

function Cell({ v, ent }: { v: string | number | null; ent: ReturnType<typeof useEntities> }) {
  if (v === null || v === undefined) return <span className="text-muted-foreground">–</span>
  if (typeof v === 'string') {
    const h = ent.map.get(v.toLowerCase().replace(/ \(.*\)/, '')) ?? ent.map.get(v.toLowerCase())
    if (h) return <Chip name={v} icon={h.icon} />
    const m = ent.maps.get(v.toLowerCase())
    return m ? <span className="inline-flex items-center gap-2"><MapBanner map={m} className="h-5 w-9 rounded" />{v}</span> : <span>{v}</span>
  }
  return <span className="tabular-nums">{Number.isInteger(v) ? v : v.toFixed(1)}</span>
}

function ToolCall({ call, running, ent }: { call: AskCall; running?: boolean; ent: ReturnType<typeof useEntities> }) {
  const [open, setOpen] = useState(false)
  const cols = call.rows[0] ? Object.keys(call.rows[0]) : []
  const isQuery = call.tool === 'cypher_query'
  return (
    <div className="rounded-lg border border-border/60 bg-background/40">
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs">
        <ChevronRight className={cn('size-3.5 text-muted-foreground transition-transform', open && 'rotate-90')} />
        <Database className="size-3.5 text-primary" />
        <span className="font-medium">{isQuery ? 'Ran a query' : call.tool.replace(/_/g, ' ')}</span>
        <span className="truncate text-muted-foreground">{isQuery ? `${call.n} row${call.n !== 1 ? 's' : ''}` : call.label}</span>
        {running && <Loader2 className="ml-auto size-3.5 animate-spin text-muted-foreground" />}
      </button>
      {open && (
        <div className="flex flex-col gap-3 border-t border-border/50 p-3">
          {call.cypher && <pre className="overflow-x-auto rounded-md bg-muted/50 p-3 font-mono text-[11px] leading-relaxed">{call.cypher}</pre>}
          {call.rows.length > 0 ? (
            <div className="max-h-80 overflow-auto rounded-md border border-border/50">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-card text-muted-foreground"><tr>{cols.map((c) => <th key={c} className="px-3 py-1.5 text-left font-medium">{c.replace(/_/g, ' ')}</th>)}</tr></thead>
                <tbody>{call.rows.map((r, i) => <tr key={i} className="border-t border-border/30">{cols.map((c) => <td key={c} className="px-3 py-1.5"><Cell v={r[c]} ent={ent} /></td>)}</tr>)}</tbody>
              </table>
            </div>
          ) : <p className="text-xs text-muted-foreground"><Rich text={call.text} ent={ent} /></p>}
          {call.n > call.rows.length && call.rows.length > 0 && <p className="text-[11px] text-muted-foreground">Showing the first {call.rows.length} of {call.n} rows.</p>}
        </div>
      )}
    </div>
  )
}

const isRate = (k: string) => /(pct|percent|rate)$/i.test(k)

/** The rows a query returned, as a table: hero and map names get their pictures, win rates get a bar around 50%. */
function ResultCard({ call, ent }: { call: AskCall; ent: ReturnType<typeof useEntities> }) {
  const [all, setAll] = useState(false)
  const [sql, setSql] = useState(false)
  const cols = call.rows[0] ? Object.keys(call.rows[0]) : []
  const rows = all ? call.rows : call.rows.slice(0, 8)
  const rate = (key: string, v: string | number | null) => {
    const raw = typeof v === 'number' ? v : NaN
    const n = /rate$/i.test(key) && raw <= 1 ? raw * 100 : raw        // a column named ...rate holds a fraction; ...pct holds a percentage
    if (Number.isNaN(n)) return <Cell v={v} ent={ent} />
    return (
      <span className="inline-flex items-center gap-2">
        <span className="relative h-1.5 w-20 rounded-full bg-muted">
          <span className="absolute inset-y-0 left-1/2 w-px bg-foreground/30" />
          <span className={cn('absolute inset-y-0 rounded-full', n >= 50 ? 'bg-emerald-500' : 'bg-orange-500')} style={{ left: `${Math.min(n, 50)}%`, width: `${Math.abs(n - 50)}%` }} />
        </span>
        <span className="w-10 tabular-nums">{n.toFixed(0)}%</span>
      </span>
    )
  }
  return (
    <div className="overflow-hidden rounded-xl border border-border/60 bg-card/50">
      <div className="flex items-center gap-2 border-b border-border/50 px-4 py-2.5 text-xs">
        <Database className="size-3.5 text-primary" />
        <b className="text-sm">Result</b>
        <span className="text-muted-foreground">{call.n} row{call.n !== 1 ? 's' : ''}</span>
        <button type="button" onClick={() => setSql(!sql)} className="ml-auto text-muted-foreground underline-offset-2 hover:text-foreground hover:underline">{sql ? 'Hide query' : 'Show query'}</button>
      </div>
      {sql && call.cypher && <pre className="overflow-x-auto border-b border-border/50 bg-muted/40 p-3 font-mono text-[11px] leading-relaxed">{call.cypher}</pre>}
      <table className="w-full text-sm">
        <thead className="text-xs text-muted-foreground"><tr>{cols.map((c) => <th key={c} className={cn('px-4 py-2 font-medium', typeof call.rows[0][c] === 'number' ? 'text-right' : 'text-left')}>{c.replace(/_/g, ' ')}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-border/30">
              {cols.map((c) => <td key={c} className={cn('px-4 py-2', typeof r[c] === 'number' && !isRate(c) && 'text-right')}>{isRate(c) ? rate(c, r[c]) : <Cell v={r[c]} ent={ent} />}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      {call.rows.length > 8 && <button type="button" onClick={() => setAll(!all)} className="w-full border-t border-border/40 py-2 text-xs text-muted-foreground hover:bg-accent/40">{all ? 'Show fewer' : `Show all ${call.rows.length} rows`}</button>}
      {call.n > call.rows.length && <p className="border-t border-border/40 px-4 py-2 text-[11px] text-muted-foreground">Showing the first {call.rows.length} of {call.n} rows.</p>}
    </div>
  )
}

function Answer({ turn, ent }: { turn: Turn; ent: ReturnType<typeof useEntities> }) {
  const j = turn.job
  const running = !j || j.state === 'running'
  return (
    <div className="flex gap-3">
      <div className="grid size-8 shrink-0 place-items-center rounded-full bg-primary/20 text-primary"><Sparkles className="size-4" /></div>
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <b className="text-foreground">Cartographer</b>
          {running ? <span className="inline-flex items-center gap-1"><Loader2 className="size-3 animate-spin" />working{j ? `, ${j.seconds} s` : ''}</span> : j?.state === 'done' ? `done in ${j.seconds} s` : ''}
        </div>
        {j?.calls.map((c, i) => (c.tool === 'cypher_query' && c.rows.length > 0 && !(running && i === j.calls.length - 1)
          ? <ResultCard key={i} call={c} ent={ent} />
          : <ToolCall key={i} call={c} ent={ent} running={running && i === j.calls.length - 1} />))}
        {running && !j?.calls.length && <div className="text-sm text-muted-foreground">Looking at the data…</div>}
        {j && j.checked.length > 0 && (
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3">
            <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-emerald-400"><Check className="size-3.5" />Checked against the data</div>
            <ul className="flex flex-col gap-1 text-sm">
              {j.checked.map((c, i) => <li key={i}><Rich text={c.text} ent={ent} />{c.matches.length > 0 && <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">{c.matches.length} matches cited</span>}</li>)}
            </ul>
            {j.removed > 0 && <p className="mt-1.5 text-[11px] text-muted-foreground">{j.removed} statement(s) removed because the numbers did not match the data.</p>}
          </div>
        )}
        {j?.framing && (
          <p className="text-sm leading-relaxed text-muted-foreground">
            <span className="mr-2 rounded-md bg-muted px-1.5 py-0.5 align-middle text-[10px] font-medium">unchecked model text</span>
            <Rich text={j.framing} ent={ent} />
            {(j.unverified ?? []).length > 0 && (
              <details className="mt-1 text-xs"><summary className="cursor-pointer">Numbers in this text that no query returned</summary>
                <span>{j.unverified!.join(', ')} (may be sums the model worked out itself)</span></details>
            )}
          </p>
        )}
        {(turn.error || j?.error) && <p className="text-sm text-destructive">{turn.error || j?.error}</p>}
      </div>
    </div>
  )
}

type Chat = { id: string; title: string; updated: number; turns: Turn[] }
const STORE = 'ask-chats'

function loadChats(): Chat[] {
  try { return JSON.parse(localStorage.getItem(STORE) ?? '[]') as Chat[] } catch { return [] }
}

export function AskChat() {
  const { data: info } = useApi<AskInfo>('ask', '')
  const { data: shell } = useApi<Shell>('shell', 'mode=2')
  const ent = useEntities(shell)
  const [params, setParams] = useSearchParams()
  const [chats, setChats] = useState<Chat[]>(loadChats)
  const [draft, setDraft] = useState(() => crypto.randomUUID())        // the id a new chat gets when its first question is sent
  const active = params.get('c') ?? draft
  const chat = chats.find((c) => c.id === active)
  const turns = chat?.turns ?? []
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const end = useRef<HTMLDivElement>(null)
  const timer = useRef<number | undefined>(undefined)

  // a question that was still running when the page went away has no answer to come back to
  useEffect(() => {
    localStorage.setItem(STORE, JSON.stringify(chats.map((c) => ({ ...c, turns: c.turns.map((t) => (t.job?.state === 'running' || (!t.job && !t.error) ? { ...t, job: null, error: t.error ?? 'Interrupted: the page was closed before the answer arrived.' } : t)) }))))
  }, [chats])
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [turns, active])
  useEffect(() => () => window.clearTimeout(timer.current), [])

  const edit = (chatId: string, fn: (c: Chat) => Chat, fallback?: Chat) =>
    setChats((cs) => (cs.some((c) => c.id === chatId) ? cs.map((c) => (c.id === chatId ? fn(c) : c)) : fallback ? [fallback, ...cs] : cs))
  const patch = (chatId: string, id: string, p: Partial<Turn>) =>
    edit(chatId, (c) => ({ ...c, updated: Date.now(), turns: c.turns.map((t) => (t.id === id ? { ...t, ...p } : t)) }))
  const poll = async (chatId: string, id: string, jobId: string) => {
    const j = await getJson<AskJob>(`/api/ask/${jobId}`)
    patch(chatId, id, { job: j })
    if (j.state === 'running') timer.current = window.setTimeout(() => void poll(chatId, id, jobId), 700)
    else setBusy(false)
  }
  const send = async (text: string) => {
    const question = text.trim()
    if (!question || busy) return
    setQ(''); setBusy(true)
    const chatId = active, id = crypto.randomUUID()
    const turn: Turn = { id, question, job: null }
    edit(chatId, (c) => ({ ...c, updated: Date.now(), turns: [...c.turns, turn] }), { id: chatId, title: question.slice(0, 60), updated: Date.now(), turns: [turn] })
    if (!params.get('c')) setParams({ c: chatId }, { replace: true })
    const r = await postJson('/api/ask/start', { question })
    const j = (await r.json()) as { id?: string; detail?: string }
    if (!r.ok || !j.id) { patch(chatId, id, { error: j.detail ?? 'Could not start' }); setBusy(false); return }
    void poll(chatId, id, j.id)
  }
  const newChat = () => { setDraft(crypto.randomUUID()); setParams({}, { replace: true }); setQ('') }
  const remove = (id: string) => {
    setChats((cs) => cs.filter((c) => c.id !== id))
    if (id === active) newChat()
  }
  const sorted = [...chats].sort((a, b) => b.updated - a.updated)
  const ago = (t: number) => { const m = Math.round((Date.now() - t) / 60000); return m < 1 ? 'now' : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : new Date(t).toLocaleDateString(undefined, { day: '2-digit', month: 'short' }) }

  return (
    <>
      <div className="grid min-h-[calc(100vh_-_190px)] gap-6 lg:grid-cols-[250px_1fr]">
        <aside className="hidden flex-col gap-2 lg:flex">
          <button type="button" onClick={newChat} className="flex items-center justify-center gap-2 rounded-xl border border-border/70 bg-card px-3 py-2 text-sm font-medium hover:border-primary/60">
            <Plus className="size-4" />New chat
          </button>
          <div className="mt-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Chats</div>
          <div className="flex flex-col gap-0.5 overflow-y-auto">
            {sorted.map((c) => (
              <div key={c.id} className={cn('group flex items-center gap-1 rounded-lg pr-1 hover:bg-accent/50', c.id === active && 'bg-accent')}>
                <button type="button" onClick={() => setParams({ c: c.id }, { replace: true })} className="min-w-0 flex-1 px-3 py-2 text-left">
                  <div className="truncate text-sm">{c.title}</div>
                  <div className="text-[11px] text-muted-foreground">{c.turns.length} question{c.turns.length !== 1 ? 's' : ''} · {ago(c.updated)}</div>
                </button>
                <button type="button" title="Delete this chat" onClick={() => remove(c.id)} className="rounded-md p-1.5 text-muted-foreground opacity-0 hover:text-destructive group-hover:opacity-100"><Trash2 className="size-3.5" /></button>
              </div>
            ))}
            {!sorted.length && <p className="px-1 text-xs text-muted-foreground">Chats are kept in this browser, so earlier chats are still here on return.</p>}
          </div>
          {sorted.length > 1 && <button type="button" onClick={() => { if (window.confirm('Delete all chats?')) { setChats([]); newChat() } }} className="mt-auto text-left text-[11px] text-muted-foreground hover:text-destructive">Clear all chats</button>}
        </aside>

        <div className="mx-auto flex w-full max-w-3xl flex-col">
          <div className="mb-2 flex items-center justify-between lg:hidden">
            <button type="button" onClick={newChat} className="inline-flex items-center gap-1.5 rounded-lg border border-border/70 px-3 py-1.5 text-xs font-medium"><Plus className="size-3.5" />New chat</button>
            {turns.length > 0 && <button type="button" onClick={() => remove(active)} className="text-xs text-muted-foreground hover:text-destructive">Delete this chat</button>}
          </div>
          <div className="flex flex-1 flex-col gap-8 pb-6">
            {turns.length === 0 && (
              <div className="my-auto flex flex-col items-center gap-5 py-16 text-center">
                <div className="grid size-12 place-items-center rounded-2xl bg-primary/20 text-primary"><Sparkles className="size-6" /></div>
                <h2 className="text-xl font-semibold tracking-tight">Ask about the stored matches</h2>
                <p className="max-w-md text-sm text-muted-foreground">Questions turn into read-only queries over the stored match history. Every number shown comes from a query that can be opened and checked.</p>
                <div className="flex max-w-xl flex-col gap-2">
                  {info?.examples.map((e) => (
                    <button key={e} type="button" onClick={() => void send(e)} className="rounded-xl border border-border/60 bg-card/50 px-4 py-2.5 text-left text-sm hover:border-primary/50 hover:bg-card">
                      <Rich text={e} ent={ent} />
                    </button>
                  ))}
                </div>
              </div>
            )}
            {turns.map((t) => (
              <div key={t.id} className="flex flex-col gap-5">
                <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-primary/20 px-4 py-2.5 text-sm"><Rich text={t.question} ent={ent} /></div>
                <Answer turn={t} ent={ent} />
              </div>
            ))}
            <div ref={end} />
          </div>
          <div className="sticky bottom-0 -mx-2 bg-gradient-to-t from-background via-background to-transparent px-2 pb-2 pt-6">
            <form onSubmit={(e) => { e.preventDefault(); void send(q) }} className="flex items-end gap-2 rounded-2xl border border-border/70 bg-card p-2 shadow-lg focus-within:border-primary/60">
              <textarea value={q} onChange={(e) => setQ(e.target.value)} rows={1} maxLength={500} placeholder="Ask a question about the matches…"
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send(q) } }}
                className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground" />
              <button type="submit" disabled={busy || !q.trim()} className="grid size-9 place-items-center rounded-xl bg-primary text-primary-foreground disabled:opacity-40">
                {busy ? <Loader2 className="size-4 animate-spin" /> : <ArrowUp className="size-4" />}
              </button>
            </form>
            <p className="mt-2 text-center text-[11px] text-muted-foreground">Model: {info?.model ?? '…'} · answers are generated by a model; the checked box and the queries are what to trust.</p>
          </div>
        </div>
      </div>
    </>
  )
}
