import { ArrowRight, Download, Link2, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'

const STEPS = [
  { icon: Link2, title: 'Find the player page', text: 'Open rivalsmeta.com, search for the player and copy the address of the profile page. It ends with a number.' },
  { icon: Download, title: 'Fetch the match history', text: 'On the Data page paste the address, read the notice, tick the box and press Fetch. Ranked comes first; quick play is optional.' },
  { icon: Sparkles, title: 'Explore', text: 'When the first fetch ends, every page fills in: rank journey, heroes, maps, patterns, squad, and the Agents page.' },
]

/** Shown instead of a page while nothing is stored yet. */
export default function FirstRun() {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 py-8">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Welcome to Rivals Atlas</h2>
        <p className="mt-2 text-sm text-muted-foreground">There is no match history here yet. Everything stays on this computer: the app downloads one player&apos;s public history, once, and works from that copy.</p>
      </div>
      <ol className="flex flex-col gap-3">
        {STEPS.map((s, i) => (
          <li key={s.title} className="flex gap-4 rounded-xl border border-border/60 bg-card/60 p-4">
            <div className="grid size-10 shrink-0 place-items-center rounded-xl bg-primary/20 text-primary"><s.icon className="size-5" /></div>
            <div>
              <div className="text-sm font-medium"><span className="mr-2 text-muted-foreground">{i + 1}.</span>{s.title}</div>
              <p className="mt-1 text-sm text-muted-foreground">{s.text}</p>
            </div>
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap items-center gap-4">
        <Button render={<Link to="/data" />} size="lg">Go to Data<ArrowRight /></Button>
        <p className="max-w-md text-xs text-muted-foreground">The first fetch of a long history takes hours because the app asks the site for one match every 3 seconds. It can be stopped and resumed, and later fetches only download new matches.</p>
      </div>
    </div>
  )
}
