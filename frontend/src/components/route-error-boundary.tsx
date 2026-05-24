import { AlertTriangle, RefreshCw } from 'lucide-react'
import { useRouteError } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

// Stored in sessionStorage to break out of an infinite reload loop. If a chunk
// is genuinely missing (not just stale), we should stop reloading after one
// attempt and show the user a real error instead of cycling forever.
//
// Cleared from RootLayout once any route mounts successfully, so a second
// chunk-load failure later in the same session also gets one auto-recovery.
export const CHUNK_RELOAD_KEY = 'mm:chunk-reload-attempted'

// Vite emits "Failed to fetch dynamically imported module" / "error loading
// dynamically imported module"; older browsers and other bundlers produce
// "Importing a module script failed" or "ChunkLoadError". Match all of them.
const CHUNK_ERROR_PATTERNS = [
  /Failed to fetch dynamically imported module/i,
  /error loading dynamically imported module/i,
  /Importing a module script failed/i,
  /ChunkLoadError/i,
]

function isChunkLoadError(error: unknown): boolean {
  if (!error) return false
  const message =
    error instanceof Error
      ? error.message
      : typeof error === 'string'
        ? error
        : ''
  return CHUNK_ERROR_PATTERNS.some((pattern) => pattern.test(message))
}

function describeError(error: unknown): string {
  if (error instanceof Error) return error.message
  if (typeof error === 'string') return error
  try {
    return JSON.stringify(error)
  } catch {
    return 'Unknown error'
  }
}

export function RouteErrorBoundary() {
  const error = useRouteError()

  // Stale-bundle case: the user's open tab loaded an old index.html that
  // references chunk filenames which no longer exist after a redeploy. Hard
  // reload to pull the fresh index.html (and the new chunk hashes).
  //
  // Guarded by sessionStorage so a chunk that is genuinely 404 (e.g. broken
  // build) doesn't trap the user in a reload loop.
  if (isChunkLoadError(error)) {
    const alreadyAttempted = sessionStorage.getItem(CHUNK_RELOAD_KEY)
    if (!alreadyAttempted) {
      sessionStorage.setItem(CHUNK_RELOAD_KEY, '1')
      window.location.reload()
      return null
    }

    return (
      <ErrorCard
        icon={<RefreshCw className="size-5" />}
        title="A new version was deployed"
        description="The page you tried to open requires a newer version of the app. Reload to pick up the latest build."
        primaryAction={{
          label: 'Reload',
          onClick: () => {
            sessionStorage.removeItem(CHUNK_RELOAD_KEY)
            window.location.reload()
          },
        }}
      />
    )
  }

  return (
    <ErrorCard
      icon={<AlertTriangle className="size-5 text-destructive" />}
      title="Something went wrong"
      description={describeError(error)}
      primaryAction={{
        label: 'Reload',
        onClick: () => window.location.reload(),
      }}
      secondaryAction={{
        label: 'Go home',
        onClick: () => {
          window.location.href = '/'
        },
      }}
    />
  )
}

type Action = { label: string; onClick: () => void }

function ErrorCard({
  icon,
  title,
  description,
  primaryAction,
  secondaryAction,
}: {
  icon: React.ReactNode
  title: string
  description: string
  primaryAction: Action
  secondaryAction?: Action
}) {
  return (
    <div className="flex min-h-[60vh] items-center justify-center p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {icon}
            {title}
          </CardTitle>
          <CardDescription className="wrap-break-word">
            {description}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button onClick={primaryAction.onClick}>{primaryAction.label}</Button>
          {secondaryAction ? (
            <Button variant="outline" onClick={secondaryAction.onClick}>
              {secondaryAction.label}
            </Button>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}
