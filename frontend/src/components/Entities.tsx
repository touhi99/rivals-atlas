import { Fragment, type ReactNode } from 'react'
import { HeroFace } from '@/components/bits'
import type { Entities } from '@/lib/entities'

export function Chip({ name, icon, size = 16 }: { name: string; icon: string | null; size?: number }) {
  return (
    <span className="mx-0.5 inline-flex items-center gap-1 rounded-full bg-muted/70 py-px pl-px pr-2 align-middle text-[0.9em] font-medium">
      <HeroFace hero={{ name, icon }} size={size} />{name}
    </span>
  )
}

export function Rich({ text, ent }: { text: string; ent: Entities }) {
  if (!ent.re) return <>{text}</>
  const parts = text.split(ent.re)
  const out: ReactNode[] = parts.map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**')) {
      const inner = p.slice(2, -2)
      const h = ent.map.get(inner.toLowerCase())
      return h ? <Chip key={i} name={h.name} icon={h.icon} /> : <b key={i}>{inner}</b>
    }
    const h = ent.map.get(p.toLowerCase())
    return h ? <Chip key={i} name={h.name} icon={h.icon} /> : <Fragment key={i}>{p}</Fragment>
  })
  return <>{out}</>
}
