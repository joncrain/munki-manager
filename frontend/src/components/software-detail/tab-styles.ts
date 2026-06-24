import { cn } from '@/lib/utils'

export const softwareDetailTabContentClass = cn(
  'space-y-4',
  'animate-in fade-in-0 slide-in-from-bottom-1 duration-300',
)

export function softwareDetailTabTrigger(activeRing: string) {
  return cn(
    'group/tab flex-none gap-2 px-4 py-2.5 min-h-11 rounded-lg border border-transparent',
    'text-muted-foreground transition-[transform,box-shadow,background-color,border-color,color] duration-200 ease-out will-change-transform',
    'hover:bg-background/80 hover:text-foreground',
    'data-[state=inactive]:hover:scale-[1.03] data-[state=inactive]:hover:-translate-y-0.5',
    'data-[state=inactive]:hover:border-border/35 data-[state=inactive]:hover:shadow-sm',
    'data-[state=active]:scale-[1.02] data-[state=active]:bg-background data-[state=active]:shadow-md',
    'data-[state=active]:border-border/60 data-[state=active]:hover:scale-[1.03]',
    'motion-reduce:data-[state=inactive]:hover:scale-100 motion-reduce:data-[state=inactive]:hover:translate-y-0',
    'motion-reduce:data-[state=active]:scale-100 motion-reduce:data-[state=active]:hover:scale-100',
    activeRing,
  )
}

export const softwareTabIconClass =
  'size-4 shrink-0 opacity-70 transition-[opacity,transform] duration-200 ease-out group-hover/tab:opacity-100 group-data-[state=inactive]/tab:group-hover/tab:scale-105 group-data-[state=active]/tab:opacity-100 group-data-[state=active]/tab:scale-110 group-data-[state=active]/tab:group-hover/tab:scale-[1.18] motion-reduce:group-hover/tab:scale-100 motion-reduce:group-data-[state=active]/tab:scale-100 motion-reduce:group-data-[state=active]/tab:group-hover/tab:scale-100'
