import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarClock, Loader2, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { useAuth } from '@/components/auth-provider'
import { AutopkgScheduleEditorDialog } from '@/components/autopkg/schedule-editor-dialog'
import { PageHeading } from '@/components/page-heading'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { type AutoPkgScheduleRead, api } from '@/lib/api'
import { formatCronExpression } from '@/lib/cron-expression'
import { formatDateTime } from '@/lib/format'
import { PAGE_KEYS } from '@/lib/page-keys'
import { cn } from '@/lib/utils'

export default function AutoPkgSchedulesPage() {
  useDocumentTitle('AutoPkg', 'Schedules')
  const { canWrite } = useAuth()
  const canEdit = canWrite(PAGE_KEYS.autopkgRuns)
  const queryClient = useQueryClient()

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<AutoPkgScheduleRead | null>(null)

  const { data: schedules, isLoading } = useQuery({
    queryKey: ['autopkg-schedules'],
    queryFn: () => api.get<AutoPkgScheduleRead[]>('/autopkg/schedules'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/autopkg/schedules/${id}`),
    onSuccess: () => {
      toast.success('Schedule deleted')
      queryClient.invalidateQueries({ queryKey: ['autopkg-schedules'] })
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const openCreate = () => {
    setEditing(null)
    setDialogOpen(true)
  }

  const openEdit = (sch: AutoPkgScheduleRead) => {
    setEditing(sch)
    setDialogOpen(true)
  }

  return (
    <div className="flex h-[calc(100vh-3rem)] min-w-0 w-full max-w-full flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <PageHeading
          icon={CalendarClock}
          accent="autopkg"
          title="AutoPkg Schedules"
        />
        {canEdit ? (
          <Button type="button" onClick={openCreate}>
            <Plus className="h-4 w-4" />
            Add schedule
          </Button>
        ) : null}
      </div>

      <p className="max-w-2xl text-sm text-muted-foreground">
        Cron schedules run in the Munki Manager API process (every minute). Use
        GitHub Actions for cloud builds or Local Mac for your own runner daemon.
        Set <code className="text-xs">SCHEDULER_ENABLED=false</code> on all but
        one replica if you run multiple API instances.
      </p>

      <div className="overflow-x-auto rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Schedule</TableHead>
              <TableHead>Timezone</TableHead>
              <TableHead>Runner</TableHead>
              <TableHead>Recipes</TableHead>
              <TableHead>Next run</TableHead>
              <TableHead>Enabled</TableHead>
              {canEdit ? <TableHead className="w-[60px]" /> : null}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={canEdit ? 8 : 7}>
                  <Loader2 className="mx-auto h-6 w-6 animate-spin text-muted-foreground" />
                </TableCell>
              </TableRow>
            ) : !schedules?.length ? (
              <TableRow>
                <TableCell
                  colSpan={canEdit ? 8 : 7}
                  className="text-center text-muted-foreground"
                >
                  No schedules yet.
                </TableCell>
              </TableRow>
            ) : (
              schedules.map((sch) => (
                <TableRow
                  key={sch.id}
                  className={cn(canEdit && 'cursor-pointer hover:bg-muted/50')}
                  onClick={() => openEdit(sch)}
                >
                  <TableCell className="font-medium">{sch.name}</TableCell>
                  <TableCell className="max-w-[280px] text-sm">
                    {formatCronExpression(sch.cron_expression)}
                  </TableCell>
                  <TableCell className="text-sm">{sch.timezone}</TableCell>
                  <TableCell>
                    <Badge variant="secondary">
                      {sch.runner_type === 'local' ? 'Local Mac' : 'GitHub'}
                    </Badge>
                  </TableCell>
                  <TableCell className="max-w-[200px] truncate text-sm">
                    {sch.recipe_names?.length
                      ? `${sch.recipe_names.length} selected`
                      : 'All enabled'}
                  </TableCell>
                  <TableCell className="text-sm">
                    {sch.next_run_at ? (
                      <span suppressHydrationWarning>
                        {formatDateTime(sch.next_run_at)}
                      </span>
                    ) : (
                      '—'
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant={sch.enabled ? 'default' : 'outline'}>
                      {sch.enabled ? 'on' : 'off'}
                    </Badge>
                  </TableCell>
                  {canEdit ? (
                    <TableCell className="text-right">
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={`Delete ${sch.name}`}
                        onClick={(e) => {
                          e.stopPropagation()
                          if (
                            typeof window !== 'undefined' &&
                            !window.confirm(`Delete schedule “${sch.name}”?`)
                          ) {
                            return
                          }
                          deleteMutation.mutate(sch.id)
                        }}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </TableCell>
                  ) : null}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <AutopkgScheduleEditorDialog
        open={dialogOpen}
        onOpenChange={(open) => {
          setDialogOpen(open)
          if (!open) setEditing(null)
        }}
        editing={editing}
        canEdit={canEdit}
      />
    </div>
  )
}
