import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ClipboardCheck,
  Copy,
  Loader2,
  Lock,
  Plus,
  ShieldAlert,
  Trash2,
  UserPlus,
} from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import {
  api,
  type EnrollmentTokenCreateBody,
  type EnrollmentTokenCreated,
  type EnrollmentTokenRow,
  type MunkiRepoBasicAuthRead,
} from '@/lib/api'

function formatDate(value: string | null): string {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}

function tokenStatus(row: EnrollmentTokenRow): {
  label: string
  className: string
} {
  if (row.redeemed_at) {
    return { label: 'Used', className: 'text-muted-foreground' }
  }
  if (row.expires_at && new Date(row.expires_at).getTime() < Date.now()) {
    return { label: 'Expired', className: 'text-destructive' }
  }
  return {
    label: 'Active',
    className: 'text-emerald-600 dark:text-emerald-400',
  }
}

export function EnrollmentTokensCard() {
  const queryClient = useQueryClient()
  const { data, isPending, isError, error } = useQuery({
    queryKey: ['enrollment-tokens'],
    queryFn: () => api.get<EnrollmentTokenRow[]>('/enroll/tokens'),
  })
  const { data: basicAuth } = useQuery({
    queryKey: ['settings', 'munki-repo-basic-auth'],
    queryFn: () =>
      api.get<MunkiRepoBasicAuthRead>('/settings/munki-repo-basic-auth'),
    staleTime: 30_000,
  })

  const basicAuthOn = basicAuth?.enabled === true
  const needsPassword = basicAuthOn && basicAuth?.env_override_active === false

  const [label, setLabel] = useState('')
  const [manifestName, setManifestName] = useState('')
  const [ttlHours, setTtlHours] = useState('24')
  const [repoPassword, setRepoPassword] = useState('')
  const [justCreated, setJustCreated] = useState<EnrollmentTokenCreated | null>(
    null,
  )
  const [copied, setCopied] = useState<'token' | 'url' | null>(null)

  const createMutation = useMutation({
    mutationFn: (body: EnrollmentTokenCreateBody) =>
      api.post<EnrollmentTokenCreated>('/enroll/tokens', body),
    onSuccess: (res) => {
      setJustCreated(res)
      setLabel('')
      setManifestName('')
      setRepoPassword('')
      void queryClient.invalidateQueries({ queryKey: ['enrollment-tokens'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete<void>(`/enroll/tokens/${id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['enrollment-tokens'] })
    },
  })

  const onCreate = (e: React.FormEvent) => {
    e.preventDefault()
    const parsedTtl = Number.parseInt(ttlHours, 10)
    const body: EnrollmentTokenCreateBody = {}
    if (label.trim()) body.label = label.trim()
    if (manifestName.trim()) body.manifest_name = manifestName.trim()
    if (Number.isFinite(parsedTtl) && parsedTtl > 0) {
      body.ttl_hours = parsedTtl
    }
    if (needsPassword && repoPassword.trim()) {
      body.repo_password = repoPassword
    }
    createMutation.mutate(body)
  }

  const copyValue = async (value: string, kind: 'token' | 'url') => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(kind)
      window.setTimeout(() => setCopied(null), 1500)
    } catch {
      // No-op: clipboard may be blocked (e.g. non-HTTPS).
    }
  }

  return (
    <Card className="sm:col-span-2">
      <CardHeader>
        <CardTitle>Client enrollment tokens</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Generate a one-time token, then send the enrollment URL to the user.
          They visit it on their Mac and download a{' '}
          <code className="text-xs">.mobileconfig</code> that points Munki at
          this server. The plaintext token is shown only once.
        </p>

        {needsPassword && (
          <div className="flex items-start gap-2 rounded-md border border-border bg-muted/30 p-3 text-xs">
            <ShieldAlert
              className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400"
              aria-hidden
            />
            <div>
              Repo Basic auth is on. Enter the current repo password below so
              the generated profile includes the{' '}
              <code className="text-xs">Authorization</code> header. The
              password is verified against the stored hash, encrypted with the
              server's <code className="text-xs">SECRET_KEY</code>, bound to
              this token only, and wiped the moment the token is redeemed.
            </div>
          </div>
        )}

        <form
          className="grid gap-3 rounded-md border border-border p-4 sm:grid-cols-[1fr_1fr_120px_auto]"
          onSubmit={onCreate}
        >
          <div className="grid gap-1.5">
            <Label htmlFor="enroll-label">Label</Label>
            <Input
              id="enroll-label"
              onChange={(e) => setLabel(e.target.value)}
              placeholder="jon MBP"
              value={label}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="enroll-manifest">Manifest name (optional)</Label>
            <Input
              id="enroll-manifest"
              onChange={(e) => setManifestName(e.target.value)}
              placeholder="site_default"
              value={manifestName}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="enroll-ttl">TTL (hours)</Label>
            <Input
              id="enroll-ttl"
              inputMode="numeric"
              onChange={(e) => setTtlHours(e.target.value)}
              value={ttlHours}
            />
          </div>
          <div className="flex items-end">
            <Button disabled={createMutation.isPending} type="submit">
              {createMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <Plus className="h-4 w-4" aria-hidden />
              )}
              {createMutation.isPending ? 'Creating…' : 'Create'}
            </Button>
          </div>
          {needsPassword && (
            <div className="grid gap-1.5 sm:col-span-full">
              <Label htmlFor="enroll-repo-password">
                Repo Basic auth password
              </Label>
              <Input
                autoComplete="off"
                id="enroll-repo-password"
                onChange={(e) => setRepoPassword(e.target.value)}
                placeholder={`Password for "${basicAuth?.username ?? 'munki'}"`}
                type="password"
                value={repoPassword}
              />
              <p className="text-xs text-muted-foreground">
                Leave blank to create a token without the{' '}
                <code className="text-xs">Authorization</code> header. You'd
                then need to distribute it to the user yourself.
              </p>
            </div>
          )}
          {createMutation.isError && (
            <p className="col-span-full text-sm text-destructive">
              {createMutation.error instanceof Error
                ? createMutation.error.message
                : 'Create failed'}
            </p>
          )}
        </form>

        {justCreated && (
          <div className="space-y-3 rounded-md border border-border bg-muted/30 p-4 text-sm">
            <div className="flex items-center gap-2 font-medium">
              <UserPlus className="h-4 w-4" aria-hidden />
              Token created — copy it now, it won't be shown again.
            </div>
            {basicAuthOn && (
              <div
                className={
                  justCreated.embeds_basic_auth
                    ? 'flex items-center gap-2 text-xs text-emerald-700 dark:text-emerald-400'
                    : 'flex items-center gap-2 text-xs text-amber-700 dark:text-amber-400'
                }
              >
                <Lock className="h-3.5 w-3.5" aria-hidden />
                {justCreated.embeds_basic_auth
                  ? 'Profile will include the Munki Authorization header.'
                  : 'Profile will NOT include an Authorization header. Distribute the repo credentials separately.'}
              </div>
            )}
            <div className="grid gap-1.5">
              <Label>Enrollment URL</Label>
              <div className="flex items-center gap-2">
                <code className="flex-1 truncate rounded bg-muted px-2 py-1.5 text-xs">
                  {justCreated.enroll_url}
                </code>
                <Button
                  onClick={() => copyValue(justCreated.enroll_url, 'url')}
                  size="sm"
                  type="button"
                  variant="secondary"
                >
                  {copied === 'url' ? (
                    <ClipboardCheck className="h-4 w-4" aria-hidden />
                  ) : (
                    <Copy className="h-4 w-4" aria-hidden />
                  )}
                  Copy URL
                </Button>
              </div>
            </div>
            <div className="grid gap-1.5">
              <Label>Raw token</Label>
              <div className="flex items-center gap-2">
                <code className="flex-1 break-all rounded bg-muted px-2 py-1.5 text-xs">
                  {justCreated.token}
                </code>
                <Button
                  onClick={() => copyValue(justCreated.token, 'token')}
                  size="sm"
                  type="button"
                  variant="secondary"
                >
                  {copied === 'token' ? (
                    <ClipboardCheck className="h-4 w-4" aria-hidden />
                  ) : (
                    <Copy className="h-4 w-4" aria-hidden />
                  )}
                  Copy token
                </Button>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              Expires {formatDate(justCreated.expires_at)}.
            </p>
          </div>
        )}

        <div className="rounded-md border border-border">
          <div className="grid grid-cols-[1fr_1fr_110px_160px_40px] items-center gap-3 border-b border-border bg-muted/30 px-3 py-2 text-xs font-medium uppercase text-muted-foreground">
            <span>Label</span>
            <span>Manifest</span>
            <span>Status</span>
            <span>Expires</span>
            <span className="sr-only">Actions</span>
          </div>
          {isPending ? (
            <div className="p-3">
              <Skeleton className="h-10 w-full" />
            </div>
          ) : isError ? (
            <p className="p-3 text-sm text-destructive">
              {error instanceof Error ? error.message : 'Failed to load'}
            </p>
          ) : (data?.length ?? 0) === 0 ? (
            <p className="p-3 text-sm text-muted-foreground">No tokens yet.</p>
          ) : (
            (data ?? []).map((row) => {
              const status = tokenStatus(row)
              return (
                <div
                  key={row.id}
                  className="grid grid-cols-[1fr_1fr_110px_160px_40px] items-center gap-3 border-b border-border px-3 py-2 text-sm last:border-b-0"
                >
                  <span className="truncate">{row.label ?? '—'}</span>
                  <span className="truncate text-muted-foreground">
                    {row.manifest_name ?? '—'}
                  </span>
                  <span className={status.className}>{status.label}</span>
                  <span className="text-muted-foreground">
                    {formatDate(row.expires_at)}
                  </span>
                  <Button
                    aria-label="Revoke token"
                    disabled={deleteMutation.isPending}
                    onClick={() => deleteMutation.mutate(row.id)}
                    size="icon"
                    type="button"
                    variant="ghost"
                  >
                    <Trash2 className="h-4 w-4" aria-hidden />
                  </Button>
                </div>
              )
            })
          )}
        </div>
      </CardContent>
    </Card>
  )
}
