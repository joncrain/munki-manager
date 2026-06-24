import { useQuery } from '@tanstack/react-query'
import { Package } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '@/components/auth-provider'
import { GlobalCommandPalette } from '@/components/global-command-palette'
import { SidebarUserMenu } from '@/components/sidebar-user-menu'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from '@/components/ui/sidebar'
import { api, type TrustPendingCountResponse } from '@/lib/api'
import { navGroups } from '@/lib/nav-config'
import { PAGE_KEYS } from '@/lib/page-keys'

function navItemIsActive(
  pathname: string,
  item: { href: string; label: string },
) {
  if (item.href === '/reporting' && item.label === 'Devices') {
    return (
      pathname === '/reporting' || pathname.startsWith('/reporting/devices/')
    )
  }
  if (item.href === '/reporting/installs') {
    return pathname.startsWith('/reporting/installs')
  }
  if (item.href === '/settings') {
    return pathname === '/settings'
  }
  return (
    pathname === item.href ||
    (item.href !== '/' && pathname.startsWith(item.href))
  )
}

export function AppSidebar() {
  const { pathname } = useLocation()
  const { canRead, loading } = useAuth()

  const canSeeApprovals = !loading && canRead(PAGE_KEYS.autopkgApprovals)
  const { data: pendingTrust } = useQuery({
    queryKey: ['pending-trust-changes-count'],
    queryFn: () =>
      api.get<TrustPendingCountResponse>(
        '/autopkg/trust-changes/pending-count',
      ),
    enabled: canSeeApprovals,
    staleTime: 30_000,
  })
  const pendingTrustCount = pendingTrust?.count ?? 0

  const showItem = (pageKey: string) => {
    // While /auth/me is loading, show full nav (headings + items).
    if (loading) return true
    return canRead(pageKey)
  }

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild tooltip="Munki Manager">
              <Link to="/">
                <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                  <Package className="size-4" />
                </div>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-semibold">Munki Manager</span>
                  <span className="truncate text-xs text-muted-foreground">
                    Munki Management
                  </span>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <GlobalCommandPalette />
        {navGroups.map((group) => {
          const visibleItems = group.items.filter((item) =>
            showItem(item.pageKey),
          )
          if (visibleItems.length === 0) {
            return null
          }
          return (
            <SidebarGroup key={group.label}>
              <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {visibleItems.map((item) => {
                    const isActive = navItemIsActive(pathname, item)
                    const showTrustBadge =
                      item.href === '/approvals' && pendingTrustCount > 0
                    return (
                      <SidebarMenuItem key={item.href}>
                        <SidebarMenuButton
                          asChild
                          isActive={isActive}
                          tooltip={item.label}
                        >
                          <Link to={item.href}>
                            <item.icon className="size-4" />
                            <span>{item.label}</span>
                          </Link>
                        </SidebarMenuButton>
                        {showTrustBadge ? (
                          <SidebarMenuBadge
                            title="Pending trust approvals"
                            className="bg-gruvbox-yellow text-primary-foreground peer-hover/menu-button:text-primary-foreground peer-data-[active=true]/menu-button:text-primary-foreground"
                          >
                            {pendingTrustCount > 99 ? '99+' : pendingTrustCount}
                          </SidebarMenuBadge>
                        ) : null}
                      </SidebarMenuItem>
                    )
                  })}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          )
        })}
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarUserMenu />
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
