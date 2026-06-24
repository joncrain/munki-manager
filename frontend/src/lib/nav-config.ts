import {
  BookOpen,
  CalendarClock,
  CheckCircle,
  ClipboardList,
  Compass,
  FileText,
  FolderOpen,
  LayoutDashboard,
  ListChecks,
  MonitorSmartphone,
  Package,
  Play,
  Settings,
  Shield,
  Sparkles,
} from 'lucide-react'
import type { ComponentType } from 'react'
import { PAGE_KEYS } from '@/lib/page-keys'

export type NavItem = {
  href: string
  label: string
  icon: ComponentType<{ className?: string }>
  pageKey: string
  group: string
  keywords?: string[]
}

export const navGroups: {
  label: string
  items: Omit<NavItem, 'group'>[]
}[] = [
  {
    label: 'Overview',
    items: [
      {
        href: '/',
        label: 'Dashboard',
        icon: LayoutDashboard,
        pageKey: PAGE_KEYS.overview,
        keywords: ['home'],
      },
    ],
  },
  {
    label: 'Munki',
    items: [
      {
        href: '/software',
        label: 'Software',
        icon: Package,
        pageKey: PAGE_KEYS.munkiSoftware,
      },
      {
        href: '/manifests',
        label: 'Manifests',
        icon: FileText,
        pageKey: PAGE_KEYS.munkiManifests,
      },
      {
        href: '/catalogs',
        label: 'Catalogs',
        icon: FolderOpen,
        pageKey: PAGE_KEYS.munkiCatalogs,
      },
    ],
  },
  {
    label: 'AutoPkg',
    items: [
      {
        href: '/autopkg/runs',
        label: 'Runs',
        icon: Play,
        pageKey: PAGE_KEYS.autopkgRuns,
      },
      {
        href: '/autopkg/schedules',
        label: 'Schedules',
        icon: CalendarClock,
        pageKey: PAGE_KEYS.autopkgRuns,
      },
      {
        href: '/autopkg/recipes',
        label: 'Recipes',
        icon: BookOpen,
        pageKey: PAGE_KEYS.autopkgRecipes,
      },
      {
        href: '/autopkg/discover',
        label: 'Discover',
        icon: Compass,
        pageKey: PAGE_KEYS.autopkgDiscover,
      },
      {
        href: '/approvals',
        label: 'Approvals',
        icon: CheckCircle,
        pageKey: PAGE_KEYS.autopkgApprovals,
      },
    ],
  },
  {
    label: 'Reporting',
    items: [
      {
        href: '/reporting',
        label: 'Devices',
        icon: MonitorSmartphone,
        pageKey: PAGE_KEYS.reportingDevices,
      },
      {
        href: '/reporting/installs',
        label: 'Installs',
        icon: ListChecks,
        pageKey: PAGE_KEYS.reportingInstalls,
      },
    ],
  },
  {
    label: 'Admin',
    items: [
      {
        href: '/audit',
        label: 'Audit Log',
        icon: ClipboardList,
        pageKey: PAGE_KEYS.adminAudit,
        keywords: ['logs'],
      },
      {
        href: '/settings',
        label: 'Settings',
        icon: Settings,
        pageKey: PAGE_KEYS.adminSettings,
      },
      {
        href: '/admin/access',
        label: 'Access',
        icon: Shield,
        pageKey: PAGE_KEYS.adminAccess,
      },
      {
        href: '/admin/ai-insights',
        label: 'AI Insights',
        icon: Sparkles,
        pageKey: PAGE_KEYS.adminAiInsights,
      },
    ],
  },
]

export function getFlatNavItems(): NavItem[] {
  return navGroups.flatMap((group) =>
    group.items.map((item) => ({ ...item, group: group.label })),
  )
}
