import type { ColumnDef, VisibilityState } from '@tanstack/react-table'
import { Link } from 'react-router-dom'
import {
  type DeploymentStatus,
  DeploymentStatusBadge,
} from '@/components/deployment-status-badge'
import { FilterBadge } from '@/components/filter-badge'
import { VersionWithLatestBadge } from '@/components/latest-version-badge'
import { SoftwareIcon } from '@/components/software-icon'
import { Badge } from '@/components/ui/badge'
import type { PkgInfoSummary } from '@/lib/api'
import { formatDate } from '@/lib/format'
import { cn } from '@/lib/utils'

export type SoftwareListColumnFilters = {
  onCategoryFilter?: (category: string) => void
  onCatalogFilter?: (catalog: string) => void
  onDeploymentStatusFilter?: (status: DeploymentStatus) => void
}

export function makeSoftwareListColumns(
  filters: SoftwareListColumnFilters = {},
): ColumnDef<PkgInfoSummary>[] {
  const { onCategoryFilter, onCatalogFilter, onDeploymentStatusFilter } =
    filters

  return [
    {
      accessorKey: 'display_name',
      header: 'Name',
      cell: ({ row }) => (
        <Link
          to={`/software/${row.original.id}`}
          className="flex items-center gap-3 font-medium hover:underline"
        >
          <SoftwareIcon
            name={row.original.name}
            displayName={row.original.display_name}
            size="sm"
          />
          <span className="truncate">
            {row.original.display_name || row.original.name}
          </span>
          {row.original.pending_metadata && (
            <Badge
              variant="outline"
              className="ml-1 shrink-0 border-amber-500 text-amber-600"
              title="Uploaded manually — finish entering version / receipts before promoting."
            >
              Manual
            </Badge>
          )}
        </Link>
      ),
      enableHiding: false,
    },
    {
      accessorKey: 'version',
      header: 'Version',
      cell: ({ row }) => (
        <VersionWithLatestBadge
          version={row.original.version}
          isLatest={row.original.is_latest}
        />
      ),
    },
    {
      accessorKey: 'category',
      header: 'Category',
      cell: ({ row }) => {
        const category = row.original.category
        if (!category) return null
        if (!onCategoryFilter) {
          return <Badge variant="outline">{category}</Badge>
        }
        return (
          <FilterBadge
            variant="outline"
            onFilter={() => onCategoryFilter(category)}
            ariaLabel={`Filter to category ${category}`}
          >
            {category}
          </FilterBadge>
        )
      },
    },
    {
      accessorKey: 'install_count',
      header: 'Installs',
      cell: ({ row }) => (
        <span className="tabular-nums text-sm">
          {row.original.install_count ?? 0}
        </span>
      ),
    },
    {
      accessorKey: 'failed_install_count',
      header: 'Failed',
      cell: ({ row }) => {
        const count = row.original.failed_install_count ?? 0
        return (
          <span
            className={cn(
              'tabular-nums text-sm',
              count > 0 && 'font-medium text-destructive',
            )}
          >
            {count}
          </span>
        )
      },
    },
    {
      accessorKey: 'developer',
      header: 'Developer',
      cell: ({ row }) => (
        <span className="truncate text-sm">{row.original.developer}</span>
      ),
    },
    {
      accessorKey: 'catalog_names',
      header: 'Catalogs',
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex gap-1">
          {row.original.catalog_names.map((catalog) =>
            onCatalogFilter ? (
              <FilterBadge
                key={catalog}
                variant="secondary"
                onFilter={() => onCatalogFilter(catalog)}
                ariaLabel={`Filter to catalog ${catalog}`}
              >
                {catalog}
              </FilterBadge>
            ) : (
              <Badge key={catalog} variant="secondary">
                {catalog}
              </Badge>
            ),
          )}
        </div>
      ),
    },
    {
      accessorKey: 'deployment_status',
      header: 'Deployment',
      enableSorting: false,
      cell: ({ row }) => {
        const deploymentStatus =
          row.original.deployment_status ?? 'not_in_production'
        return (
          <DeploymentStatusBadge
            deploymentStatus={deploymentStatus}
            shardPercent={row.original.shard_percent ?? null}
            isFirstProductionDeploy={row.original.is_first_production_deploy}
            inManifest={row.original.in_manifest}
            onFilter={
              onDeploymentStatusFilter
                ? () => onDeploymentStatusFilter(deploymentStatus)
                : undefined
            }
          />
        )
      },
    },
    {
      accessorKey: 'minimum_os_version',
      header: 'Min OS',
      cell: ({ row }) => (
        <span className="font-mono text-sm text-muted-foreground">
          {row.original.minimum_os_version ?? '—'}
        </span>
      ),
    },
    {
      accessorKey: 'installer_type',
      header: 'Installer Type',
      cell: ({ row }) =>
        row.original.installer_type ? (
          <Badge variant="outline">{row.original.installer_type}</Badge>
        ) : (
          <span className="text-sm text-muted-foreground">—</span>
        ),
    },
    {
      accessorKey: 'unattended_install',
      header: 'Unattended',
      cell: ({ row }) => (
        <Badge
          variant={row.original.unattended_install ? 'default' : 'outline'}
        >
          {row.original.unattended_install ? 'Yes' : 'No'}
        </Badge>
      ),
    },
    {
      accessorKey: 'unattended_uninstall',
      header: 'Unattended Uninstall',
      cell: ({ row }) => (
        <Badge
          variant={row.original.unattended_uninstall ? 'default' : 'outline'}
        >
          {row.original.unattended_uninstall ? 'Yes' : 'No'}
        </Badge>
      ),
    },
    {
      accessorKey: 'restart_action',
      header: 'Restart Action',
      cell: ({ row }) =>
        row.original.restart_action ? (
          <Badge variant="secondary">{row.original.restart_action}</Badge>
        ) : (
          <span className="text-sm text-muted-foreground">—</span>
        ),
    },
    {
      accessorKey: 'updated_at',
      header: 'Updated',
      cell: ({ row }) => (
        <span
          suppressHydrationWarning
          className="text-sm text-muted-foreground"
        >
          {formatDate(row.original.updated_at)}
        </span>
      ),
    },
  ]
}

export const softwareListDefaultColumnVisibility: VisibilityState = {
  display_name: true,
  version: true,
  category: true,
  install_count: true,
  failed_install_count: true,
  developer: false,
  catalog_names: true,
  deployment_status: true,
  minimum_os_version: false,
  installer_type: false,
  unattended_install: false,
  unattended_uninstall: false,
  restart_action: false,
  updated_at: true,
}
