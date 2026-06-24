import { useQuery } from '@tanstack/react-query'
import { useSetAtom } from 'jotai'
import {
  BookOpen,
  ClipboardList,
  Command as CommandIcon,
  MonitorSmartphone,
  Package,
  Search,
} from 'lucide-react'
import * as React from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/components/auth-provider'
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from '@/components/ui/command'
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenuButton,
  useSidebar,
} from '@/components/ui/sidebar'
import { useDebounce } from '@/hooks/use-debounce'
import {
  autopkgRecipesPageListAtom,
  defaultAutopkgRecipesPageListState,
} from '@/lib/atoms/autopkg-recipes-page-list'
import {
  defaultSoftwarePageListState,
  softwarePageListAtom,
} from '@/lib/atoms/software-page-list'
import {
  auditListPath,
  autopkgDetailPath,
  autopkgListPath,
  deviceDetailPath,
  deviceListPath,
  type EntitySearchType,
  quickCheckAutopkg,
  quickCheckDevice,
  quickCheckSoftware,
  type SearchScope,
  softwareDetailPath,
  softwareListPath,
  suggestAudit,
  suggestAutopkg,
  suggestDevices,
  suggestSoftware,
} from '@/lib/global-search'
import { getFlatNavItems, type NavItem } from '@/lib/nav-config'
import { PAGE_KEYS } from '@/lib/page-keys'
import { cn } from '@/lib/utils'

const scopeLabels: Record<SearchScope, string> = {
  all: 'All',
  software: 'Software',
  autopkg: 'AutoPkg',
  device: 'Devices',
  audit: 'Audit',
}

const searchExamples = ['Firefox', 'munki', 'hostname']

const scopePageKeys: Record<EntitySearchType, string> = {
  software: PAGE_KEYS.munkiSoftware,
  autopkg: PAGE_KEYS.autopkgRecipes,
  device: PAGE_KEYS.reportingDevices,
  audit: PAGE_KEYS.adminAudit,
}

function normalizeSearchValue(value: string) {
  return value.toLowerCase().trim()
}

function navItemMatchesQuery(item: NavItem, query: string) {
  const normalizedQuery = normalizeSearchValue(query)
  if (!normalizedQuery) return false

  return [item.label, item.href, item.group, ...(item.keywords ?? [])].some(
    (value) => normalizeSearchValue(value).includes(normalizedQuery),
  )
}

function ShortcutHint({ shortcutKey }: { shortcutKey: string }) {
  const [isApplePlatform, setIsApplePlatform] = React.useState(false)

  React.useEffect(() => {
    setIsApplePlatform(/Mac|iPhone|iPad|iPod/.test(navigator.platform))
  }, [])

  return (
    <kbd className="inline-flex items-center gap-1 rounded border bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
      {isApplePlatform ? (
        <CommandIcon className="h-3 w-3" aria-label="Command" />
      ) : (
        <span>Ctrl</span>
      )}
      <span>{shortcutKey}</span>
    </kbd>
  )
}

export function GlobalCommandPalette() {
  const navigate = useNavigate()
  const sidebar = useSidebar()
  const { canRead, loading } = useAuth()
  const setSoftwareListState = useSetAtom(softwarePageListAtom)
  const setAutopkgListState = useSetAtom(autopkgRecipesPageListAtom)

  const [open, setOpen] = React.useState(false)
  const [searchTerm, setSearchTerm] = React.useState('')
  const [activeScope, setActiveScope] = React.useState<SearchScope>('all')
  const [pendingSearchType, setPendingSearchType] =
    React.useState<EntitySearchType | null>(null)

  const trimmedSearchTerm = searchTerm.trim()
  const debouncedSearchTerm = useDebounce(trimmedSearchTerm, 200)

  React.useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setOpen((current) => !current)
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  const canSearchScope = React.useCallback(
    (scope: EntitySearchType) => {
      if (loading) return true
      return canRead(scopePageKeys[scope])
    },
    [canRead, loading],
  )

  const availableSearchTypes = React.useMemo(() => {
    const types: EntitySearchType[] = []
    if (canSearchScope('software')) types.push('software')
    if (canSearchScope('autopkg')) types.push('autopkg')
    if (canSearchScope('device')) types.push('device')
    if (canSearchScope('audit')) types.push('audit')
    return types
  }, [canSearchScope])

  const availableScopes = React.useMemo(
    () => ['all', ...availableSearchTypes] as SearchScope[],
    [availableSearchTypes],
  )

  const scopedSearchTypes = React.useMemo(
    () =>
      activeScope === 'all'
        ? availableSearchTypes
        : availableSearchTypes.includes(activeScope as EntitySearchType)
          ? [activeScope as EntitySearchType]
          : [],
    [activeScope, availableSearchTypes],
  )

  React.useEffect(() => {
    if (!availableScopes.includes(activeScope)) {
      setActiveScope('all')
    }
  }, [activeScope, availableScopes])

  React.useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!open) return
      if ((event.metaKey || event.ctrlKey) && event.key === '.') {
        event.preventDefault()
        setActiveScope((current) => {
          const currentIndex = availableScopes.indexOf(current)
          const nextIndex =
            currentIndex === -1
              ? 0
              : (currentIndex + 1) % availableScopes.length
          return availableScopes[nextIndex] ?? 'all'
        })
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [availableScopes, open])

  const navItems = React.useMemo(() => {
    if (loading) return getFlatNavItems()
    return getFlatNavItems().filter((item) => canRead(item.pageKey))
  }, [canRead, loading])

  const navigationMatches = React.useMemo(
    () =>
      activeScope === 'all'
        ? navItems
            .filter((item) => navItemMatchesQuery(item, trimmedSearchTerm))
            .slice(0, 8)
        : [],
    [activeScope, navItems, trimmedSearchTerm],
  )

  const shouldFetchSuggestions = open && debouncedSearchTerm.length >= 2
  const canSearchSoftware = scopedSearchTypes.includes('software')
  const canSearchAutopkg = scopedSearchTypes.includes('autopkg')
  const canSearchDevices = scopedSearchTypes.includes('device')
  const canSearchAudit = scopedSearchTypes.includes('audit')
  const isAuditScope = activeScope === 'audit'

  const softwareSuggestions = useQuery({
    queryKey: ['global-search-software', debouncedSearchTerm],
    queryFn: () => suggestSoftware(debouncedSearchTerm, 5),
    enabled: shouldFetchSuggestions && canSearchSoftware,
  })

  const autopkgSuggestions = useQuery({
    queryKey: ['global-search-autopkg', debouncedSearchTerm],
    queryFn: () => suggestAutopkg(debouncedSearchTerm, 5),
    enabled: shouldFetchSuggestions && canSearchAutopkg,
  })

  const deviceSuggestions = useQuery({
    queryKey: ['global-search-devices', debouncedSearchTerm],
    queryFn: () => suggestDevices(debouncedSearchTerm, 5),
    enabled: shouldFetchSuggestions && canSearchDevices,
  })

  const auditSuggestions = useQuery({
    queryKey: ['global-search-audit', debouncedSearchTerm],
    queryFn: () => suggestAudit(debouncedSearchTerm, 5),
    enabled: shouldFetchSuggestions && canSearchAudit,
  })

  const isFetchingSuggestions =
    softwareSuggestions.isFetching ||
    autopkgSuggestions.isFetching ||
    deviceSuggestions.isFetching ||
    auditSuggestions.isFetching

  const closeAndNavigate = React.useCallback(
    (href: string) => {
      setOpen(false)
      setSearchTerm('')
      navigate(href)
    },
    [navigate],
  )

  const runEntitySearch = React.useCallback(
    async (searchType: EntitySearchType) => {
      const q = searchTerm.trim()
      if (!q || pendingSearchType) return

      setPendingSearchType(searchType)

      try {
        if (searchType === 'audit') {
          closeAndNavigate(auditListPath(q))
          return
        }

        if (searchType === 'software') {
          const result = await quickCheckSoftware(q)
          if (result.count === 1 && result.id) {
            closeAndNavigate(softwareDetailPath(result.id))
          } else {
            setSoftwareListState({
              ...defaultSoftwarePageListState,
              search: q,
              page: 1,
            })
            closeAndNavigate(softwareListPath(q))
          }
          return
        }

        if (searchType === 'autopkg') {
          const result = await quickCheckAutopkg(q)
          if (result.count === 1 && result.id) {
            closeAndNavigate(autopkgDetailPath(result.id))
          } else {
            setAutopkgListState({
              ...defaultAutopkgRecipesPageListState,
              search: q,
              page: 1,
            })
            closeAndNavigate(autopkgListPath(q))
          }
          return
        }

        const result = await quickCheckDevice(q)
        if (result.count === 1 && result.id) {
          closeAndNavigate(deviceDetailPath(result.id))
        } else {
          closeAndNavigate(deviceListPath(q))
        }
      } catch {
        const fallback =
          searchType === 'software'
            ? softwareListPath(q)
            : searchType === 'autopkg'
              ? autopkgListPath(q)
              : searchType === 'device'
                ? deviceListPath(q)
                : auditListPath(q)
        closeAndNavigate(fallback)
      } finally {
        setPendingSearchType(null)
      }
    },
    [
      closeAndNavigate,
      pendingSearchType,
      searchTerm,
      setAutopkgListState,
      setSoftwareListState,
    ],
  )

  const isCollapsed = sidebar.state === 'collapsed' && !sidebar.isMobile

  return (
    <>
      <SidebarGroup className="pt-1">
        <SidebarGroupContent>
          {isCollapsed ? (
            <SidebarMenuButton
              variant="default"
              className="h-8 w-8 p-0"
              onClick={() => setOpen(true)}
              tooltip="Search"
            >
              <Search className="h-4 w-4 text-muted-foreground" />
            </SidebarMenuButton>
          ) : (
            <button
              type="button"
              onClick={() => setOpen(true)}
              className={cn(
                'group/search flex h-8 w-full items-center gap-2 rounded-md border border-sidebar-border bg-background px-2 text-left text-sm text-muted-foreground shadow-xs transition-colors',
                'hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring',
              )}
            >
              <Search className="h-4 w-4 shrink-0" />
              <span className="min-w-0 flex-1 truncate font-extralight">
                Search
              </span>
              <span className="opacity-0 transition-opacity group-hover/search:opacity-100 group-focus-visible/search:opacity-100">
                <ShortcutHint shortcutKey="K" />
              </span>
            </button>
          )}
        </SidebarGroupContent>
      </SidebarGroup>

      <CommandDialog
        open={open}
        onOpenChange={setOpen}
        title="Search"
        description="Search pages, software, AutoPkg recipes, devices, and audit log."
        shouldFilter={false}
        contentClassName="top-[12vh] w-[min(920px,calc(100vw-2rem))] max-w-none translate-y-0"
        commandClassName="[&_[cmdk-group-heading]]:px-4 [&_[cmdk-input-wrapper]]:px-4 [&_[cmdk-input]]:h-16 [&_[cmdk-input]]:text-base [&_[cmdk-item]]:px-4"
      >
        <CommandInput
          placeholder={
            activeScope === 'all'
              ? 'Search pages or type a software, recipe, device, or audit query...'
              : `Search ${scopeLabels[activeScope].toLowerCase()}...`
          }
          value={searchTerm}
          onValueChange={setSearchTerm}
        />
        <div className="flex items-center gap-3 border-b px-4 py-2.5">
          <span className="shrink-0 font-medium text-[11px] text-muted-foreground uppercase tracking-wide">
            Scope
          </span>
          <div className="flex w-fit flex-wrap gap-1 rounded-md bg-muted/40 p-1">
            {availableScopes.map((scope) => (
              <button
                key={scope}
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => setActiveScope(scope)}
                className={cn(
                  'rounded-sm px-2.5 py-1 text-xs transition-colors',
                  activeScope === scope
                    ? 'bg-background text-foreground shadow-xs'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {scopeLabels[scope]}
              </button>
            ))}
          </div>
          <div className="ml-auto">
            <ShortcutHint shortcutKey="." />
          </div>
        </div>
        <CommandList className="min-h-[440px] max-h-[68vh]">
          {trimmedSearchTerm && (
            <CommandEmpty>
              {trimmedSearchTerm.length >= 2 && isFetchingSuggestions
                ? 'Searching...'
                : `No ${scopeLabels[activeScope].toLowerCase()} results found.`}
            </CommandEmpty>
          )}

          {!trimmedSearchTerm && (
            <div className="flex min-h-[360px] items-center justify-center px-6 text-center">
              <div className="max-w-md space-y-3">
                <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
                  <Search className="h-5 w-5" />
                </div>
                <div className="space-y-1">
                  <p className="font-medium text-sm">
                    Search across Munki Manager
                  </p>
                  <p className="text-muted-foreground text-sm">
                    Try software name, recipe identifier, device hostname, audit
                    entity, or a page name.
                  </p>
                </div>
                <div className="flex flex-wrap justify-center gap-1.5 pt-1">
                  {searchExamples.map((example) => (
                    <button
                      key={example}
                      type="button"
                      onClick={() => setSearchTerm(example)}
                      className="rounded-full border border-border px-2 py-0.5 text-muted-foreground text-xs transition-colors hover:bg-accent hover:text-accent-foreground"
                    >
                      {example}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {trimmedSearchTerm.length >= 2 && !isAuditScope && (
            <>
              <CommandGroup heading="Top Matches">
                {isFetchingSuggestions && (
                  <CommandItem disabled value="searching">
                    <Search className="h-4 w-4" />
                    <span>
                      Searching {scopeLabels[activeScope].toLowerCase()}...
                    </span>
                  </CommandItem>
                )}

                {canSearchSoftware &&
                  softwareSuggestions.data?.map((result) => (
                    <CommandItem
                      key={`software-${result.id}`}
                      value={[
                        'software',
                        result.name,
                        result.display_name,
                        result.version,
                      ]
                        .filter(Boolean)
                        .join(' ')}
                      onSelect={() =>
                        closeAndNavigate(softwareDetailPath(result.id))
                      }
                    >
                      <Package className="h-4 w-4" />
                      <div className="flex min-w-0 flex-col">
                        <span className="truncate">
                          {result.display_name || result.name}
                        </span>
                        <span className="truncate text-xs text-muted-foreground">
                          {[result.name, result.version]
                            .filter(Boolean)
                            .join(' - ')}
                        </span>
                      </div>
                      <CommandShortcut>Software</CommandShortcut>
                    </CommandItem>
                  ))}

                {canSearchAutopkg &&
                  autopkgSuggestions.data?.map((result) => (
                    <CommandItem
                      key={`autopkg-${result.id}`}
                      value={[
                        'autopkg',
                        'recipe',
                        result.name,
                        result.identifier,
                        result.parent_recipe,
                      ]
                        .filter(Boolean)
                        .join(' ')}
                      onSelect={() =>
                        closeAndNavigate(autopkgDetailPath(result.id))
                      }
                    >
                      <BookOpen className="h-4 w-4" />
                      <div className="flex min-w-0 flex-col">
                        <span className="truncate">
                          {result.pkginfo_display_name || result.name}
                        </span>
                        <span className="truncate text-xs text-muted-foreground">
                          {[result.identifier, result.trust_status]
                            .filter(Boolean)
                            .join(' - ')}
                        </span>
                      </div>
                      <CommandShortcut>AutoPkg</CommandShortcut>
                    </CommandItem>
                  ))}

                {canSearchDevices &&
                  deviceSuggestions.data?.map((result) => (
                    <CommandItem
                      key={`device-${result.id}`}
                      value={[
                        'device',
                        result.hostname,
                        result.serial_number,
                        result.manifest_name,
                      ]
                        .filter(Boolean)
                        .join(' ')}
                      onSelect={() =>
                        closeAndNavigate(deviceDetailPath(result.id))
                      }
                    >
                      <MonitorSmartphone className="h-4 w-4" />
                      <div className="flex min-w-0 flex-col">
                        <span className="truncate">
                          {result.hostname || result.serial_number || 'Device'}
                        </span>
                        <span className="truncate text-xs text-muted-foreground">
                          {[result.serial_number, result.manifest_name]
                            .filter(Boolean)
                            .join(' - ')}
                        </span>
                      </div>
                      <CommandShortcut>Device</CommandShortcut>
                    </CommandItem>
                  ))}
              </CommandGroup>
              <CommandSeparator />
            </>
          )}

          {trimmedSearchTerm.length >= 2 && canSearchAudit && (
            <>
              {!isAuditScope && <CommandSeparator />}
              <CommandGroup heading={isAuditScope ? 'Top Matches' : 'Audit'}>
                {canSearchAudit && isAuditScope && isFetchingSuggestions && (
                  <CommandItem disabled value="searching-audit">
                    <Search className="h-4 w-4" />
                    <span>Searching audit log...</span>
                  </CommandItem>
                )}
                {auditSuggestions.data?.map((result) => (
                  <CommandItem
                    key={`audit-${result.id}`}
                    value={[
                      'audit',
                      result.action,
                      result.entity_type,
                      result.entity_name,
                      result.entity_id,
                      result.user_email,
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    onSelect={() =>
                      closeAndNavigate(auditListPath(trimmedSearchTerm))
                    }
                  >
                    <ClipboardList className="h-4 w-4" />
                    <div className="flex min-w-0 flex-col">
                      <span className="truncate">
                        {result.entity_name || result.entity_id}
                      </span>
                      <span className="truncate text-xs text-muted-foreground">
                        {[result.action, result.entity_type, result.user_email]
                          .filter(Boolean)
                          .join(' - ')}
                      </span>
                    </div>
                    <CommandShortcut>Audit</CommandShortcut>
                  </CommandItem>
                ))}
              </CommandGroup>
              {!isAuditScope && <CommandSeparator />}
            </>
          )}

          {navigationMatches.length > 0 && (
            <CommandGroup heading="Navigation">
              {navigationMatches.map((item) => {
                const Icon = item.icon
                return (
                  <CommandItem
                    key={item.href}
                    value={[item.label, item.href, item.group]
                      .filter(Boolean)
                      .join(' ')}
                    onSelect={() => closeAndNavigate(item.href)}
                  >
                    <Icon className="h-4 w-4" />
                    <div className="flex min-w-0 flex-col">
                      <span className="truncate">{item.label}</span>
                      <span className="truncate text-xs text-muted-foreground">
                        {item.group}
                      </span>
                    </div>
                    <CommandShortcut>Page</CommandShortcut>
                  </CommandItem>
                )
              })}
            </CommandGroup>
          )}

          {trimmedSearchTerm && scopedSearchTypes.length > 0 && (
            <>
              {navigationMatches.length > 0 && <CommandSeparator />}
              <CommandGroup heading="Search More">
                {scopedSearchTypes.includes('software') && (
                  <CommandItem
                    value={`search all software ${trimmedSearchTerm}`}
                    onSelect={() => runEntitySearch('software')}
                    disabled={pendingSearchType !== null}
                  >
                    <Package className="h-4 w-4" />
                    <span>Search all software for "{trimmedSearchTerm}"</span>
                    {pendingSearchType === 'software' && (
                      <CommandShortcut>Searching</CommandShortcut>
                    )}
                  </CommandItem>
                )}
                {scopedSearchTypes.includes('autopkg') && (
                  <CommandItem
                    value={`search all autopkg recipes ${trimmedSearchTerm}`}
                    onSelect={() => runEntitySearch('autopkg')}
                    disabled={pendingSearchType !== null}
                  >
                    <BookOpen className="h-4 w-4" />
                    <span>Search all recipes for "{trimmedSearchTerm}"</span>
                    {pendingSearchType === 'autopkg' && (
                      <CommandShortcut>Searching</CommandShortcut>
                    )}
                  </CommandItem>
                )}
                {scopedSearchTypes.includes('device') && (
                  <CommandItem
                    value={`search all devices ${trimmedSearchTerm}`}
                    onSelect={() => runEntitySearch('device')}
                    disabled={pendingSearchType !== null}
                  >
                    <MonitorSmartphone className="h-4 w-4" />
                    <span>Search all devices for "{trimmedSearchTerm}"</span>
                    {pendingSearchType === 'device' && (
                      <CommandShortcut>Searching</CommandShortcut>
                    )}
                  </CommandItem>
                )}
                {scopedSearchTypes.includes('audit') && (
                  <CommandItem
                    value={`search all audit ${trimmedSearchTerm}`}
                    onSelect={() => runEntitySearch('audit')}
                    disabled={pendingSearchType !== null}
                  >
                    <ClipboardList className="h-4 w-4" />
                    <span>Search audit log for "{trimmedSearchTerm}"</span>
                    {pendingSearchType === 'audit' && (
                      <CommandShortcut>Searching</CommandShortcut>
                    )}
                  </CommandItem>
                )}
              </CommandGroup>
            </>
          )}
        </CommandList>
      </CommandDialog>
    </>
  )
}
