import { BarChart3, Download, Grid3x3, Map as MapIcon, MessageSquare, Search, Swords, Users } from 'lucide-react'
import type { CSSProperties, ReactNode } from 'react'
import { Link, NavLink } from 'react-router-dom'
import FilterBar from '@/components/FilterBar'
import FirstRun from '@/components/FirstRun'
import { Separator } from '@/components/ui/separator'
import {
  Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent, SidebarGroupLabel, SidebarHeader, SidebarInset,
  SidebarMenu, SidebarMenuButton, SidebarMenuItem, SidebarProvider, SidebarRail, SidebarTrigger,
} from '@/components/ui/sidebar'
import { useApi, type Shell } from '@/lib/api'
import { useFilters } from '@/lib/filters'

const GROUPS = [
  { label: 'Dashboard', items: [
    { to: '/', label: 'Overview', icon: BarChart3 },
    { to: '/heroes', label: 'Heroes', icon: Swords },
    { to: '/maps', label: 'Maps', icon: MapIcon },
  ] },
  { label: 'Analysis', items: [
    { to: '/patterns', label: 'Patterns', icon: Grid3x3 },
    { to: '/squad', label: 'Squad', icon: Users },
    { to: '/explore', label: 'Explore', icon: Search },
    { to: '/ask', label: 'Ask', icon: MessageSquare },
  ] },
  { label: 'Data', items: [{ to: '/data', label: 'Data', icon: Download }] },
]

export default function Layout({ title, children, bar = true, needsData = true }: { title: string; children: ReactNode; bar?: boolean; needsData?: boolean }) {
  const { query } = useFilters()
  const { data: shell } = useApi<Shell>('shell', 'mode=2')
  const empty = needsData && shell?.has_data === false
  return (
    <SidebarProvider style={{ '--sidebar-width': '15rem', '--header-height': '3.5rem' } as CSSProperties}>
      <Sidebar variant="inset" collapsible="icon">
        <SidebarHeader>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton size="lg" render={<Link to="/" />}>
                <img src="/static/logo.svg" alt="" className="size-8 rounded-lg shadow-[0_2px_12px_rgba(16,185,129,.45)]" />
                <span className="text-base font-semibold tracking-tight">Rivals Atlas</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarHeader>
        <SidebarContent>
          {GROUPS.map((g) => (
            <SidebarGroup key={g.label}>
              <SidebarGroupLabel>{g.label}</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {g.items.map(({ to, label, icon: Icon }) => (
                    <NavLink key={to} end={to === '/'} to={{ pathname: to, search: query }}>
                      {({ isActive }) => (
                        <SidebarMenuItem>
                          <SidebarMenuButton isActive={isActive} tooltip={label} render={<span />}>
                            <Icon /><span>{label}</span>
                          </SidebarMenuButton>
                        </SidebarMenuItem>
                      )}
                    </NavLink>
                  ))}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          ))}
        </SidebarContent>
        <SidebarFooter>
          <p className="px-2 text-[11px] text-muted-foreground/70 group-data-[collapsible=icon]:hidden">by touhi99</p>
        </SidebarFooter>
        <SidebarRail />
      </Sidebar>
      <SidebarInset>
        <header className="sticky top-0 z-30 flex min-h-(--header-height) shrink-0 flex-wrap items-center gap-2 rounded-t-xl border-b bg-background/95 px-4 py-2 backdrop-blur-md lg:px-6">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="mx-1 data-[orientation=vertical]:h-4" />
          <h1 className="mr-3 text-base font-medium">{title}</h1>
          {bar && !empty && <FilterBar />}
        </header>
        <div className="@container/main flex flex-1 flex-col">
          <main className="mx-auto flex w-full max-w-[1500px] flex-col gap-4 p-4 lg:gap-6 lg:p-6">{empty ? <FirstRun /> : children}</main>
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
