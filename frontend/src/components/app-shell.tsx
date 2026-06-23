import { useAtom } from 'jotai'
import { Suspense } from 'react'
import { useLocation } from 'react-router-dom'
import { AppSidebar } from '@/components/app-sidebar'
import { DemoBanner } from '@/components/demo-banner'
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from '@/components/ui/sidebar'
import { sidebarOpenAtom } from '@/lib/atoms/ui'

function pathHidesSidebar(pathname: string | null): boolean {
  if (!pathname) return false
  if (pathname === '/login' || pathname === '/register') return true
  if (pathname.startsWith('/auth/')) return true
  if (pathname === '/enroll' || pathname.startsWith('/enroll/')) return true
  return false
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation()
  const [sidebarOpen, setSidebarOpen] = useAtom(sidebarOpenAtom)
  const authLayout = pathHidesSidebar(pathname)

  if (authLayout) {
    return (
      <main className="min-h-svh min-w-0 flex-1">
        <Suspense>{children}</Suspense>
      </main>
    )
  }

  return (
    <SidebarProvider onOpenChange={setSidebarOpen} open={sidebarOpen}>
      <AppSidebar />
      <SidebarInset>
        <header className="flex h-12 shrink-0 items-center gap-2 border-b px-4 md:hidden">
          <SidebarTrigger />
          <span className="font-semibold">Munki Manager</span>
        </header>
        <main className="min-w-0 flex-1 overflow-auto">
          <Suspense>
            <div className="container mx-auto min-w-0 max-w-full p-4 sm:p-6">
              <DemoBanner />
              {children}
            </div>
          </Suspense>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
