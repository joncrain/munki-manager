import type { ReactNode } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

interface SettingsFormCardProps {
  title: string
  description?: ReactNode
  isPending?: boolean
  isError?: boolean
  error?: unknown
  skeletonClassName?: string
  children: ReactNode
}

export function SettingsFormCard({
  title,
  description,
  isPending = false,
  isError = false,
  error,
  skeletonClassName = 'h-40 w-full',
  children,
}: SettingsFormCardProps) {
  return (
    <Card className="sm:col-span-1">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {description}
        {isPending ? (
          <Skeleton className={skeletonClassName} />
        ) : isError ? (
          <p className="text-sm text-destructive">
            {error instanceof Error ? error.message : 'Failed to load'}
          </p>
        ) : (
          children
        )}
      </CardContent>
    </Card>
  )
}
