import { ArrowRight, Database, FileJson, Layers, LayoutDashboard } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Panel, Spinner } from '@/components/bits'
import Layout from '@/components/Layout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Progress } from '@/components/ui/progress'
import { getJson, postJson, useApi, type DataInfo, type FetchJob } from '@/lib/api'

function Stage({ icon, label, big, lines }: { icon: ReactNode; label: string; big: number | string; lines: string[] }) {
  return (
    <div className="min-w-[190px] flex-1 rounded-xl border border-border/60 bg-background/40 p-4">
      <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">{icon}{label}</div>
      <div className="mt-1 text-3xl font-semibold tracking-tight tabular-nums">{typeof big === 'number' ? big.toLocaleString() : big}</div>
      <div className="mt-1 flex flex-col text-xs text-muted-foreground">{lines.map((l) => <span key={l}>{l}</span>)}</div>
    </div>
  )
}

const sel = 'h-8 rounded-md border border-input bg-background px-2 text-sm'

export default function DataPage() {
  const { data: d, error } = useApi<DataInfo>('data', '')
  const [profile, setProfile] = useState<string | null>(null)
  const [mode, setMode] = useState('2')
  const [pace, setPace] = useState('gentle')
  const [limit, setLimit] = useState('')
  const [ok, setOk] = useState<boolean | null>(null)
  const [job, setJob] = useState<FetchJob>({ state: 'idle' })
  const [err, setErr] = useState('')
  const timer = useRef<number | undefined>(undefined)

  const poll = async () => {
    const s = await getJson<FetchJob>('/api/fetch/status')
    setJob(s)
    if (s.state === 'running') timer.current = window.setTimeout(poll, 1000)
  }
  useEffect(() => { void poll(); return () => window.clearTimeout(timer.current) }, [])

  const start = async () => {
    setErr('')
    const r = await postJson('/api/fetch/start', { profile: profile ?? d?.profile ?? '', mode, limit, pace, consent: ok ?? d?.consented ?? false })
    if (!r.ok) { setErr(((await r.json()) as { detail?: string }).detail ?? 'Could not start'); return }
    void poll()
  }

  const running = job.state === 'running'
  const pctDone = job.total ? Math.round((100 * (job.done ?? 0)) / job.total) : 0
  const x = d?.inv
  return (
    <Layout title="Data" bar={false} needsData={false}>
      {error && <p className="text-sm text-destructive">Could not load: {error}</p>}
      {!d && !error && <Spinner />}
      {d && x && (
        <>
          <Panel title="Stored data" hint={`${x.db.mb} MB database`}>
            <div className="flex flex-wrap items-stretch gap-3">
              <Stage icon={<FileJson className="size-3.5" />} label="1 · Raw files" big={x.raw.matches}
                lines={['match documents', `${x.raw.history} history pages`, x.raw.meta ? 'hero meta' : 'no hero meta yet']} />
              <ArrowRight className="size-4 self-center text-muted-foreground" />
              <Stage icon={<Database className="size-3.5" />} label="2 · Database" big={x.db.matches}
                lines={[`matches · ${x.db.seasons} seasons`, `${x.db.player_lines.toLocaleString()} player lines · ${x.db.hero_lines.toLocaleString()} hero lines`, `${x.db.bans.toLocaleString()} ban and pick entries`]} />
              <ArrowRight className="size-4 self-center text-muted-foreground" />
              <Stage icon={<Layers className="size-3.5" />} label="3 · Derived" big={x.derived.edges}
                lines={['hero pair edges', `${x.derived.meta_heroes} heroes in the meta${x.derived.meta_age_h != null ? ` (${x.derived.meta_age_h} h old)` : ''}`, 'patterns and findings computed on demand']} />
              <ArrowRight className="size-4 self-center text-muted-foreground" />
              <Stage icon={<LayoutDashboard className="size-3.5" />} label="4 · Views" big="7" lines={['Overview · Heroes · Maps', 'Patterns · Squad', 'Explore · Data']} />
            </div>
            <div className="mt-4 flex flex-wrap gap-3">
              {Object.entries(x.db.modes).map(([n, c]) => <Mini key={n} label={`${n} matches`} v={c} />)}
              <Mini label="Other players" v={x.db.players} /><Mini label="With a local name" v={x.db.named} />
              {x.db.no_history > 0 && <Mini label="Without map or season" v={x.db.no_history} />}
            </div>
            <p className="mt-3 text-xs text-muted-foreground">Everything after step 1 can be rebuilt from the raw files with <code>rivals-atlas import</code>.</p>
          </Panel>

          <Panel title="Fetch match history" hint={`${d.matches} matches stored`}>
            <details className="mb-3 text-sm">
              <summary className="cursor-pointer text-primary">How do I find the player page?</summary>
              <ol className="mt-2 list-decimal pl-5 text-muted-foreground leading-7">
                <li>Open rivalsmeta.com and search for the player name.</li><li>Open the player's profile.</li>
                <li>Copy the address from the browser's address bar (it looks like <code>https://rivalsmeta.com/player/1234567890</code>) and paste it below.</li>
              </ol>
            </details>
            <pre className="mb-4 whitespace-pre-line rounded-lg bg-muted/50 p-4 font-sans text-sm text-muted-foreground">{d.notice}</pre>
            <div className="mb-3 flex flex-wrap items-end gap-4">
              <label className="flex flex-col gap-1 text-xs text-muted-foreground">Player page
                <Input className="w-[380px]" value={profile ?? d.profile} onChange={(e) => setProfile(e.target.value)} placeholder="paste the address of the player page, or its number" /></label>
              <label className="flex flex-col gap-1 text-xs text-muted-foreground">Mode
                <select className={sel} value={mode} onChange={(e) => setMode(e.target.value)}><option value="2">Ranked</option><option value="1">Quick play</option></select></label>
              <label className="flex flex-col gap-1 text-xs text-muted-foreground">Pace
                <select className={sel} value={pace} onChange={(e) => setPace(e.target.value)}><option value="gentle">Gentle (1 per 3 seconds)</option><option value="normal">Normal (1 per second)</option></select></label>
              <label className="flex flex-col gap-1 text-xs text-muted-foreground">At most (new matches)
                <Input className="w-24" inputMode="numeric" placeholder="all" value={limit} onChange={(e) => setLimit(e.target.value)} /></label>
            </div>
            <label className="mb-4 flex items-center gap-2 text-sm">
              <input type="checkbox" checked={ok ?? d.consented} onChange={(e) => setOk(e.target.checked)} />
              I have read the notice above and I am responsible for following the site's terms.
            </label>
            <Button onClick={start} disabled={running}>{running ? 'Fetching…' : 'Fetch'}</Button>
            <Progress value={job.state === 'done' ? 100 : pctDone} className="mt-4" />
            <p className="mt-2 text-sm text-muted-foreground">
              {job.state === 'idle' && 'Idle.'}
              {(job.state === 'running' || job.state === 'error') && `${job.stage ? `${job.stage}: ` : ''}${job.message ?? ''}`}
              {job.state === 'done' && <>Done: {job.result?.imported} matches in the database. <Link to="/" className="text-primary underline">Open the dashboard</Link></>}
            </p>
            {(err || job.error) && <p className="mt-2 text-sm text-destructive">{err || job.error}</p>}
            <p className="mt-3 text-xs text-muted-foreground">Large histories are kinder to the site at the gentle pace. The fetch can be repeated or resumed at any time: stored matches are skipped, so only new ones are downloaded. It stops at the first refusal from the site. The same thing runs from a terminal with <code>rivals-atlas fetch</code>.</p>
          </Panel>
        </>
      )}
    </Layout>
  )
}

function Mini({ label, v }: { label: string; v: number }) {
  return <div className="rounded-lg border border-border/50 px-3 py-2"><div className="text-[11px] capitalize text-muted-foreground">{label}</div><div className="text-lg font-semibold tabular-nums">{v.toLocaleString()}</div></div>
}
