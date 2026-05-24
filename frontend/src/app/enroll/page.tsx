import { useQuery } from '@tanstack/react-query'
import {
  CheckCircle2,
  Download,
  Info,
  Loader2,
  Monitor,
  ShieldCheck,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { api, type EnrollmentStatus, redeemEnrollmentProfile } from '@/lib/api'

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export default function EnrollPage() {
  useDocumentTitle('Enroll')
  const [searchParams] = useSearchParams()
  const initialToken = searchParams.get('token') ?? ''
  const [token, setToken] = useState(initialToken)
  const [manifestName, setManifestName] = useState('')
  const [downloading, setDownloading] = useState(false)
  const [downloaded, setDownloaded] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setToken(initialToken)
  }, [initialToken])

  const { data: status } = useQuery({
    queryKey: ['enroll-status'],
    queryFn: () => api.get<EnrollmentStatus>('/enroll/status'),
    staleTime: 60_000,
  })

  const onDownload = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setDownloaded(false)
    if (!token.trim()) {
      setError('Paste the enrollment token your admin sent you.')
      return
    }
    setDownloading(true)
    try {
      const blob = await redeemEnrollmentProfile(token.trim(), manifestName)
      downloadBlob(blob, 'munki-manager-enroll.mobileconfig')
      setDownloaded(true)
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to download profile',
      )
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="mx-auto flex min-h-svh w-full max-w-2xl flex-col gap-6 p-6">
      <header className="flex items-center gap-3">
        <div className="flex aspect-square size-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Monitor className="size-5" aria-hidden />
        </div>
        <div>
          <h1 className="text-xl font-semibold">
            Enroll this Mac in Munki Manager
          </h1>
          <p className="text-sm text-muted-foreground">
            Install a small configuration profile so Munki reports into this
            server.
          </p>
        </div>
      </header>

      {status?.server_base_url && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Server</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex items-center gap-2">
              <ShieldCheck
                className="h-4 w-4 text-muted-foreground"
                aria-hidden
              />
              <span className="text-muted-foreground">Base URL</span>
              <code className="ml-auto break-all rounded bg-muted px-2 py-1 text-xs">
                {status.server_base_url}
              </code>
            </div>
            {status.repo_basic_auth_enabled && (
              <div className="flex items-start gap-2 rounded-md border border-border bg-muted/30 p-3 text-xs">
                <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                <div>
                  This server requires HTTP Basic auth for Munki repository
                  requests.{' '}
                  {status.profile_embeds_basic_auth
                    ? 'The profile you download will include the required header.'
                    : 'Ask your admin for the Munki Authorization header to add after install.'}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">1. Download your profile</CardTitle>
          <CardDescription>
            Your one-time token is consumed on download. If you need a new one,
            ask your admin.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={onDownload}>
            <div className="grid gap-1.5">
              <Label htmlFor="enroll-token">Enrollment token</Label>
              <Input
                autoComplete="off"
                id="enroll-token"
                onChange={(e) => setToken(e.target.value)}
                placeholder="Paste the token your admin sent"
                value={token}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="enroll-manifest">
                Manifest name{' '}
                <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Input
                autoComplete="off"
                id="enroll-manifest"
                onChange={(e) => setManifestName(e.target.value)}
                placeholder="Leave blank to use this Mac's hostname"
                value={manifestName}
              />
              <p className="text-xs text-muted-foreground">
                Overrides the Munki{' '}
                <code className="text-xs">ClientIdentifier</code> if set.
              </p>
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            {downloaded && (
              <div className="flex items-start gap-2 rounded-md border border-border bg-emerald-50 p-3 text-sm dark:bg-emerald-950/40">
                <CheckCircle2
                  className="mt-0.5 h-4 w-4 text-emerald-600 dark:text-emerald-400"
                  aria-hidden
                />
                <div>
                  Profile downloaded. Continue with the install steps below.
                </div>
              </div>
            )}
            <Button disabled={downloading} type="submit">
              {downloading ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <Download className="h-4 w-4" aria-hidden />
              )}
              {downloading ? 'Preparing…' : 'Download .mobileconfig'}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">2. Install the profile</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <ol className="list-decimal space-y-2 pl-5">
            <li>
              Double-click{' '}
              <code className="text-xs">munki-manager-enroll.mobileconfig</code>{' '}
              in your Downloads folder.
            </li>
            <li>
              Open <b>System Settings</b> → <b>Privacy &amp; Security</b> →{' '}
              <b>Profiles</b> (at the bottom).
            </li>
            <li>
              Select <b>Munki Manager client settings</b> and click{' '}
              <b>Install</b>. Enter your Mac password when prompted.
            </li>
          </ol>
          <p className="text-xs text-muted-foreground">
            On Macs enrolled with MDM, your admin may deploy this profile
            through MDM instead of asking you to install it by hand.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            3. Install Munki (if you don't have it)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p>
            Download the latest Munki installer from{' '}
            <a
              className="text-primary underline underline-offset-2"
              href="https://github.com/munki/munki/releases/latest"
              rel="noopener noreferrer"
              target="_blank"
            >
              github.com/munki/munki/releases
            </a>
            , run it, then trigger the first check-in:
          </p>
          <pre className="overflow-x-auto rounded-md bg-muted px-3 py-2 text-xs">
            {`sudo /usr/local/munki/managedsoftwareupdate --checkonly`}
          </pre>
          <p className="text-xs text-muted-foreground">
            Optional: also install the Munki Manager postflight from the{' '}
            <code className="text-xs">agent/</code> folder so this Mac appears
            in Reporting.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
