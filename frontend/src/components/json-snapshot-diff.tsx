import { Differ, Viewer } from 'json-diff-kit'
import { useMemo } from 'react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import 'json-diff-kit/dist/viewer.css'

const snapshotDiffer = new Differ({
  showModifications: true,
  arrayDiffMethod: 'lcs',
})

function SnapshotDiffLegend({ className }: { className?: string }) {
  return (
    <fieldset
      className={cn(
        'm-0 min-w-0 border-0 p-0',
        'flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground',
        className,
      )}
    >
      <legend className="sr-only">Diff color legend</legend>
      <span className="inline-flex items-center gap-1.5">
        <span
          className="size-3 shrink-0 rounded-sm border border-red-600/40 bg-red-500/30"
          aria-hidden
        />
        Removed
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span
          className="size-3 shrink-0 rounded-sm border border-emerald-600/40 bg-emerald-500/30"
          aria-hidden
        />
        Added
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span
          className="size-3 shrink-0 rounded-sm border border-amber-600/40 bg-amber-500/30"
          aria-hidden
        />
        Modified
      </span>
    </fieldset>
  )
}

export function JsonSnapshotDiff({
  before,
  after,
}: {
  before: unknown
  after: unknown
}) {
  const diff = useMemo(
    () => snapshotDiffer.diff(before ?? null, after ?? null),
    [before, after],
  )

  return (
    <div className="overflow-hidden rounded-md border">
      <div className="flex flex-col gap-2 border-b bg-muted/30 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
        <SnapshotDiffLegend />
        <p className="text-xs text-muted-foreground">
          Side-by-side comparison · inline highlights show word-level edits
        </p>
      </div>
      <div className="grid grid-cols-2 border-b text-xs font-semibold tracking-wide uppercase">
        <div className="border-r bg-red-500/10 px-3 py-2 text-red-800 dark:text-red-300">
          Before
        </div>
        <div className="bg-emerald-500/10 px-3 py-2 text-emerald-800 dark:text-emerald-300">
          After
        </div>
      </div>
      <ScrollArea className="h-[min(50vh,420px)] overscroll-contain bg-background">
        <div className="audit-json-diff p-2" translate="no">
          <Viewer
            diff={diff}
            indent={2}
            lineNumbers
            highlightInlineDiff
            hideUnchangedLines={{ threshold: 6, margin: 2 }}
            inlineDiffOptions={{ mode: 'word', wordSeparator: ' ' }}
          />
        </div>
      </ScrollArea>
    </div>
  )
}
