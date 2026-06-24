import { useQueryClient } from '@tanstack/react-query'
import { Loader2, Upload } from 'lucide-react'
import { useId, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  type CatalogRead,
  type PkgInfoDetail,
  uploadSoftwareFile,
} from '@/lib/api'
import { deriveAutoName } from '@/lib/pkginfo-name'

interface SoftwareUploadDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  catalogs: CatalogRead[]
}

const _formatSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024)
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

/**
 * Direct-upload dialog for ``/software``: streams a pkg/dmg to
 * ``POST /api/v1/munki/upload``; the backend hashes, optionally extracts
 * basic metadata from a flat .pkg, uploads the bytes to the configured
 * storage backend, and creates a ``PkgInfo`` row.
 */
export function SoftwareUploadDialog({
  open,
  onOpenChange,
  catalogs,
}: SoftwareUploadDialogProps) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [file, setFile] = useState<File | null>(null)
  const [displayName, setDisplayName] = useState('')
  const [name, setName] = useState('')
  const [category, setCategory] = useState('')
  const [developer, setDeveloper] = useState('')
  const [description, setDescription] = useState('')
  const [unattended, setUnattended] = useState(false)
  const [repoSubdir, setRepoSubdir] = useState('')
  const [selectedCatalogs, setSelectedCatalogs] = useState<string[]>([
    'testing',
  ])
  const [progress, setProgress] = useState<{
    loaded: number
    total: number
  } | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const autoName = useMemo(
    () => deriveAutoName({ displayName, filename: file?.name }),
    [displayName, file?.name],
  )

  const fileInputId = useId()
  const dispNameId = useId()
  const nameId = useId()
  const categoryId = useId()
  const devId = useId()
  const descId = useId()
  const unattendedId = useId()
  const subdirId = useId()

  const reset = () => {
    setFile(null)
    setDisplayName('')
    setName('')
    setCategory('')
    setDeveloper('')
    setDescription('')
    setUnattended(false)
    setRepoSubdir('')
    setSelectedCatalogs(['testing'])
    setProgress(null)
    setSubmitting(false)
  }

  const onSubmit = async () => {
    if (!file) {
      toast.error('Choose a file to upload')
      return
    }
    if (!displayName.trim()) {
      toast.error('Display name is required')
      return
    }
    setSubmitting(true)
    try {
      const result: PkgInfoDetail = await uploadSoftwareFile(
        file,
        {
          display_name: displayName.trim(),
          name: name.trim() || undefined,
          catalogs: selectedCatalogs.join(',') || 'testing',
          category: category.trim() || undefined,
          developer: developer.trim() || undefined,
          description: description.trim() || undefined,
          unattended_install: unattended,
          munki_repo_subdir: repoSubdir.trim() || undefined,
        },
        (loaded, total) => setProgress({ loaded, total }),
      )
      if (result.pending_metadata) {
        toast.success('Uploaded — please complete metadata', {
          description:
            "We couldn't extract a version/receipts. Edit the new entry to fill in the missing fields before promoting.",
        })
      } else {
        toast.success(`Uploaded ${result.name} ${result.version}`)
      }
      queryClient.invalidateQueries({ queryKey: ['pkginfo'] })
      queryClient.invalidateQueries({ queryKey: ['catalogs'] })
      onOpenChange(false)
      reset()
      navigate(`/software/${result.id}`)
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Upload failed'
      toast.error(msg)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!submitting) {
          onOpenChange(o)
          if (!o) reset()
        }
      }}
    >
      <DialogContent className="flex max-h-[90dvh] flex-col gap-0 overflow-hidden p-0 sm:max-h-[85vh] sm:max-w-2xl">
        <DialogHeader className="shrink-0 border-b px-6 pt-6 pr-14 pb-4">
          <DialogTitle className="flex items-center gap-2">
            <Upload className="h-5 w-5" />
            Upload software
          </DialogTitle>
          <DialogDescription>
            Drop a <code>.pkg</code> or <code>.dmg</code>; the backend hashes
            it, extracts basic metadata where possible, uploads to the
            configured storage backend, and creates a software entry. .dmg files
            always need manual metadata afterwards.
          </DialogDescription>
        </DialogHeader>

        <div className="grid min-h-0 flex-1 gap-4 overflow-y-auto px-6 py-4">
          <div className="grid gap-2">
            <Label htmlFor={fileInputId}>Installer file</Label>
            <Input
              id={fileInputId}
              type="file"
              accept=".pkg,.mpkg,.dmg"
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null
                setFile(f)
                if (f && !displayName) {
                  const stem = f.name.replace(/\.(pkg|mpkg|dmg)$/i, '')
                  setDisplayName(stem)
                }
              }}
            />
            {file && (
              <p className="text-xs text-muted-foreground">
                {file.name} — {_formatSize(file.size)}
              </p>
            )}
          </div>

          <div className="grid gap-2 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor={dispNameId}>Display name *</Label>
              <Input
                id={dispNameId}
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Slack"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor={nameId}>
                Name <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Input
                id={nameId}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={autoName || 'auto-derived from display name'}
              />
              <p className="text-xs text-muted-foreground">
                {name.trim() ? (
                  <>
                    Manifest items will reference <code>{name.trim()}</code>.
                  </>
                ) : autoName ? (
                  <>
                    Will be auto-derived as <code>{autoName}</code> — what
                    manifests reference. Override here if you want a different
                    name.
                  </>
                ) : (
                  <>
                    Munki manifest entries reference this exact name. We strip a
                    trailing <code>-&lt;version&gt;</code> from the auto default
                    so the client can resolve it.
                  </>
                )}
              </p>
            </div>
          </div>

          <div className="grid gap-2 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor={categoryId}>Category</Label>
              <Input
                id={categoryId}
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="Productivity"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor={devId}>Developer</Label>
              <Input
                id={devId}
                value={developer}
                onChange={(e) => setDeveloper(e.target.value)}
                placeholder="Slack Technologies"
              />
            </div>
          </div>

          <div className="grid gap-2">
            <Label htmlFor={descId}>Description</Label>
            <Textarea
              id={descId}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="Short description shown in Managed Software Center."
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor={subdirId}>
              Repo subdirectory{' '}
              <span className="text-muted-foreground">(optional)</span>
            </Label>
            <Input
              id={subdirId}
              value={repoSubdir}
              onChange={(e) => setRepoSubdir(e.target.value)}
              placeholder="apps/Slack"
            />
            <p className="text-xs text-muted-foreground">
              Path under <code>pkgs/</code> where the file will be stored. Leave
              blank to upload to the root of <code>pkgs/</code>. This also
              becomes the <code>installer_item_location</code> in the pkginfo.
            </p>
          </div>

          <div className="grid gap-2">
            <Label>Catalogs</Label>
            <div className="flex flex-wrap gap-2">
              {catalogs
                .slice()
                .sort((a, b) => a.name.localeCompare(b.name))
                .map((cat) => {
                  const catalogCheckboxId = `upload-catalog-${cat.id}`
                  return (
                    <label
                      key={cat.id}
                      htmlFor={catalogCheckboxId}
                      className="flex cursor-pointer items-center gap-2 rounded-md border px-2 py-1 text-sm hover:bg-muted/60"
                    >
                      <Checkbox
                        id={catalogCheckboxId}
                        checked={selectedCatalogs.includes(cat.name)}
                        onCheckedChange={(v) => {
                          const on = !!v
                          setSelectedCatalogs((prev) =>
                            on
                              ? prev.includes(cat.name)
                                ? prev
                                : [...prev, cat.name]
                              : prev.filter((n) => n !== cat.name),
                          )
                        }}
                      />
                      <span>{cat.name}</span>
                    </label>
                  )
                })}
            </div>
            <p className="text-xs text-muted-foreground">
              Defaults to <code>testing</code> when none are selected.
            </p>
          </div>

          <label
            htmlFor={unattendedId}
            className="flex cursor-pointer items-center gap-2 rounded-md border px-2 py-1.5 text-sm hover:bg-muted/60"
          >
            <Checkbox
              id={unattendedId}
              checked={unattended}
              onCheckedChange={(v) => setUnattended(!!v)}
            />
            <span>Allow unattended install</span>
          </label>

          {progress && progress.total > 0 && (
            <div className="grid gap-1">
              <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full bg-primary transition-[width]"
                  style={{
                    width: `${Math.min(100, (progress.loaded / progress.total) * 100).toFixed(1)}%`,
                  }}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                {_formatSize(progress.loaded)} / {_formatSize(progress.total)}
              </p>
            </div>
          )}
        </div>

        <DialogFooter className="shrink-0 gap-2 border-t bg-background px-6 py-4 sm:rounded-b-lg">
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={submitting}
            className="w-full sm:w-auto"
          >
            Cancel
          </Button>
          <Button
            type="button"
            onClick={onSubmit}
            disabled={submitting || !file}
            className="w-full sm:w-auto"
          >
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Uploading…
              </>
            ) : (
              <>
                <Upload className="h-4 w-4" />
                Upload
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
