import type { ColumnDef } from '@tanstack/react-table'
import { PanelRightClose, PanelRightOpen, Table2 } from 'lucide-react'
import { DataTable } from '@/components/data-table'
import { Button } from '@/components/ui/button'
import type { InsightsTableData, InsightsToolUsed } from '@/lib/api'

type InsightsDataPanelProps = {
  tableData: InsightsTableData | null
  toolsUsed: InsightsToolUsed[]
  open: boolean
  onToggle: () => void
}

function tableColumns(
  columns: string[],
): ColumnDef<Record<string, string | number | null>>[] {
  return columns.map((col) => ({
    accessorKey: col,
    header: col.replace(/_/g, ' '),
    cell: ({ row }) => {
      const value = row.original[col]
      if (value == null || value === '') return '—'
      return String(value)
    },
  }))
}

function tableRows(
  columns: string[],
  rows: (string | number | null)[][],
): Record<string, string | number | null>[] {
  return rows.map((row) =>
    Object.fromEntries(columns.map((col, i) => [col, row[i] ?? null])),
  )
}

export function InsightsDataPanel({
  tableData,
  toolsUsed,
  open,
  onToggle,
}: InsightsDataPanelProps) {
  const hasTable = Boolean(tableData?.columns?.length && tableData.rows.length)

  if (!open) {
    return (
      <div className="flex shrink-0 flex-col items-center border-l border-border bg-muted/20 px-2 py-3">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={onToggle}
          aria-label="Show data panel"
          title="Show data"
        >
          <PanelRightOpen className="h-4 w-4" />
        </Button>
        {hasTable && (
          <span className="mt-2 text-[10px] text-muted-foreground [writing-mode:vertical-rl]">
            Data
          </span>
        )}
      </div>
    )
  }

  return (
    <aside className="flex min-h-0 w-full shrink-0 flex-col border-l border-border bg-muted/10 lg:w-[35%]">
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <Table2
            className="h-4 w-4 shrink-0 text-muted-foreground"
            aria-hidden
          />
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold">Query data</h2>
            <p className="truncate text-xs text-muted-foreground">
              Tabular results from tool calls
            </p>
          </div>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={onToggle}
          aria-label="Hide data panel"
          title="Hide data"
        >
          <PanelRightClose className="h-4 w-4" />
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {toolsUsed.length > 0 && (
          <div className="mb-4 space-y-2">
            <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Tools used
            </h3>
            <ul className="space-y-2">
              {toolsUsed.map((tool) => (
                <li
                  key={`${tool.name}-${tool.summary}`}
                  className="rounded-lg border border-border bg-card px-3 py-2 text-xs"
                >
                  <span className="font-medium">{tool.name}</span>
                  <span className="mt-0.5 block text-muted-foreground">
                    {tool.summary}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {hasTable && tableData ? (
          <DataTable
            columns={tableColumns(tableData.columns)}
            data={tableRows(tableData.columns, tableData.rows)}
            emptyMessage="No rows"
          />
        ) : (
          <p className="text-sm text-muted-foreground">
            No tabular data for this answer yet. Ask a question that returns a
            list or version breakdown to see rows here.
          </p>
        )}
      </div>
    </aside>
  )
}
