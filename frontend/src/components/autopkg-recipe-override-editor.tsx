import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import yaml from 'js-yaml'
import {
  Braces,
  Download,
  ExternalLink,
  FileCode2,
  FileText,
  GripVertical,
  History,
  ListTree,
  Loader2,
  Package,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from 'lucide-react'
import { parse as plistParse } from 'plist'
import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { EntityAuditTrail } from '@/components/audit/entity-audit-trail'
import { PkginfoIconUpload } from '@/components/pkginfo-icon-upload'
import { SoftwareIcon } from '@/components/software-icon'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import {
  type AutoPkgRecipeRead,
  api,
  apiGetText,
  type CatalogRead,
  type PromotionChannelRead,
} from '@/lib/api'
import {
  extractNonPkginfoInput,
  extractPkginfo,
  parseCatalogListInput,
  recipeIconUploadBasename,
  recipeInputDict,
} from '@/lib/autopkg-recipe'
import { publicApiBaseUrl } from '@/lib/public-api-base'
import { githubBlobUrlForTrustEntry } from '@/lib/trust-github'
import { cn } from '@/lib/utils'

const recipeDetailTabContentClass = cn(
  'space-y-4',
  'animate-in fade-in-0 slide-in-from-bottom-1 duration-300',
)

function recipeDetailTabTrigger(activeRing: string) {
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

const recipeTabIconClass =
  'size-4 shrink-0 opacity-70 transition-[opacity,transform] duration-200 ease-out group-hover/tab:opacity-100 group-data-[state=inactive]/tab:group-hover/tab:scale-105 group-data-[state=active]/tab:opacity-100 group-data-[state=active]/tab:scale-110 group-data-[state=active]/tab:group-hover/tab:scale-[1.18] motion-reduce:group-hover/tab:scale-100 motion-reduce:group-data-[state=active]/tab:scale-100 motion-reduce:group-data-[state=active]/tab:group-hover/tab:scale-100'

// ── Structured key/value editor ──────────────────────────────────────────

type KVEntry = { id: string; key: string; value: string }

let _kvId = 0
function nextKvId() {
  return `kv-${++_kvId}`
}

function kvFromDict(
  dict: Record<string, unknown> | null | undefined,
): KVEntry[] {
  if (!dict || typeof dict !== 'object') return []
  return Object.entries(dict).map(([key, value]) => ({
    id: nextKvId(),
    key,
    value: typeof value === 'string' ? value : JSON.stringify(value),
  }))
}

function kvToDict(entries: KVEntry[]): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  for (const { key, value } of entries) {
    if (!key.trim()) continue
    // AutoPkg Input values are conventionally strings in upstream recipes
    // (e.g. ``MAJOR_VERSION = "5"`` in Blender.download.recipe). Bare
    // numeric input here used to be coerced to a JSON number by
    // ``JSON.parse``, which then serialized as ``<integer>`` in the runner
    // plist and crashed AutoPkg's ``%VAR%`` substitution
    // (``TypeError: sequence item 1: expected str instance, int found``).
    // Keep bare numeric values as strings; only parse as JSON for clear
    // JSON literals (objects, arrays, quoted strings, booleans, null).
    const trimmed = value.trim()
    const looksLikeJsonLiteral =
      trimmed.startsWith('{') ||
      trimmed.startsWith('[') ||
      trimmed.startsWith('"') ||
      trimmed === 'true' ||
      trimmed === 'false' ||
      trimmed === 'null'
    if (looksLikeJsonLiteral) {
      try {
        result[key.trim()] = JSON.parse(value)
        continue
      } catch {
        // fall through to plain string
      }
    }
    result[key.trim()] = value
  }
  return result
}

function KeyValueEditor({
  entries,
  onChange,
  keyPlaceholder = 'KEY',
  valuePlaceholder = 'Value',
  readOnly = false,
}: {
  entries: KVEntry[]
  onChange: (entries: KVEntry[]) => void
  keyPlaceholder?: string
  valuePlaceholder?: string
  readOnly?: boolean
}) {
  const update = (index: number, field: 'key' | 'value', val: string) => {
    const next = [...entries]
    next[index] = { ...next[index], [field]: val }
    onChange(next)
  }

  const remove = (index: number) => {
    onChange(entries.filter((_, i) => i !== index))
  }

  const add = () => {
    onChange([...entries, { id: nextKvId(), key: '', value: '' }])
  }

  return (
    <div className="space-y-2">
      {entries.length === 0 && !readOnly && (
        <p className="text-xs text-muted-foreground py-1">
          No entries. Click + to add one.
        </p>
      )}
      {entries.length === 0 && readOnly && (
        <p className="text-xs text-muted-foreground py-1">No entries.</p>
      )}
      {entries.map((entry, i) => (
        <div key={entry.id} className="flex items-start gap-2">
          {!readOnly && (
            <GripVertical className="mt-2.5 h-4 w-4 shrink-0 text-muted-foreground/50" />
          )}
          <Input
            value={entry.key}
            onChange={(e) => update(i, 'key', e.target.value)}
            placeholder={keyPlaceholder}
            className="font-mono text-sm flex-2"
            readOnly={readOnly}
          />
          <Input
            value={entry.value}
            onChange={(e) => update(i, 'value', e.target.value)}
            placeholder={valuePlaceholder}
            className="font-mono text-sm flex-3"
            readOnly={readOnly}
          />
          {!readOnly && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="shrink-0 mt-0.5"
              aria-label={`Remove ${entry.key}`}
              onClick={() => remove(i)}
            >
              <Trash2 className="h-4 w-4 text-destructive" />
            </Button>
          )}
        </div>
      ))}
      {!readOnly && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={add}
          className="w-full"
        >
          <Plus className="h-4 w-4" />
          Add Entry
        </Button>
      )}
    </div>
  )
}

// ── Trust info viewer ────────────────────────────────────────────────────

function TrustInfoViewer({
  trustInfo,
}: {
  trustInfo: Record<string, unknown> | null | undefined
}) {
  if (!trustInfo) {
    return (
      <p className="text-sm text-muted-foreground py-2">
        No trust info recorded. Create or update the override to generate trust
        info.
      </p>
    )
  }

  const parentRecipes =
    (trustInfo.parent_recipes as Record<string, Record<string, string>>) ?? {}
  const processors =
    (trustInfo.non_core_processors as Record<string, Record<string, string>>) ??
    {}

  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-sm font-medium mb-2">Parent Recipes</h4>
        {Object.keys(parentRecipes).length === 0 ? (
          <p className="text-xs text-muted-foreground">None</p>
        ) : (
          <div className="space-y-2">
            {Object.entries(parentRecipes).map(([identifier, info]) => {
              const fileUrl = githubBlobUrlForTrustEntry(
                trustInfo,
                trustInfo,
                'parent_recipes',
                identifier,
              )
              return (
                <div
                  key={identifier}
                  className="rounded-md border bg-muted/30 px-3 py-2"
                >
                  {fileUrl ? (
                    <a
                      href={fileUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 font-mono text-sm font-medium text-primary hover:underline"
                    >
                      {identifier}
                      <ExternalLink
                        className="h-3.5 w-3.5 shrink-0"
                        aria-hidden
                      />
                    </a>
                  ) : (
                    <p className="font-mono text-sm font-medium">
                      {identifier}
                    </p>
                  )}
                  {info.github_repo && (
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">
                      <span className="text-muted-foreground/70">Repo:</span>{' '}
                      <a
                        href={`https://github.com/${info.github_repo}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:underline"
                      >
                        {info.github_repo}
                      </a>
                      {info.github_path && (
                        <>
                          {' / '}
                          <span className="font-mono">{info.github_path}</span>
                        </>
                      )}
                    </p>
                  )}
                  <p className="mt-0.5 truncate text-xs text-muted-foreground">
                    <span className="text-muted-foreground/70">SHA256:</span>{' '}
                    <code className="bg-muted px-1 rounded">
                      {info.sha256_hash}
                    </code>
                  </p>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div>
        <h4 className="text-sm font-medium mb-2">Non-Core Processors</h4>
        {Object.keys(processors).length === 0 ? (
          <p className="text-xs text-muted-foreground">None</p>
        ) : (
          <div className="space-y-2">
            {Object.entries(processors).map(([name, info]) => (
              <div
                key={name}
                className="rounded-md border bg-muted/30 px-3 py-2"
              >
                <p className="font-mono text-sm font-medium">{name}</p>
                {info.github_repo && (
                  <p className="mt-0.5 truncate text-xs text-muted-foreground">
                    <span className="text-muted-foreground/70">Repo:</span>{' '}
                    {info.github_repo}
                    {info.github_path && (
                      <>
                        {' / '}
                        <span className="font-mono">{info.github_path}</span>
                      </>
                    )}
                  </p>
                )}
                <p className="mt-0.5 truncate text-xs text-muted-foreground">
                  <span className="text-muted-foreground/70">SHA256:</span>{' '}
                  <code className="bg-muted px-1 rounded">
                    {info.sha256_hash}
                  </code>
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── pkginfo field helpers ─────────────────────────────────────────────────

const PKGINFO_TEXT_FIELDS = [
  { key: 'description', label: 'Description', multiline: true },
  { key: 'display_name', label: 'Display Name', multiline: false },
  { key: 'developer', label: 'Developer', multiline: false },
  { key: 'name', label: 'Package Name', multiline: false },
  { key: 'category', label: 'Category', multiline: false },
  { key: 'minimum_os_version', label: 'Minimum OS Version', multiline: false },
  { key: 'maximum_os_version', label: 'Maximum OS Version', multiline: false },
  { key: 'uninstall_method', label: 'Uninstall Method', multiline: false },
] as const

const PKGINFO_BOOL_FIELDS = [
  { key: 'unattended_install', label: 'Unattended Install' },
  { key: 'unattended_uninstall', label: 'Unattended Uninstall' },
  { key: 'autoremove', label: 'Auto Remove' },
  { key: 'uninstallable', label: 'Uninstallable' },
] as const

const PKGINFO_LIST_FIELDS = [
  { key: 'catalogs', label: 'Catalogs' },
  { key: 'blocking_applications', label: 'Blocking Applications' },
  { key: 'requires', label: 'Requires' },
  { key: 'update_for', label: 'Update For' },
] as const

function PkginfoEditor({
  pkginfo,
  onUpdate,
  catalogNames,
  onIconFileUploaded,
  packageBasenameForIcons,
  readOnly = false,
}: {
  pkginfo: Record<string, unknown>
  onUpdate: (key: string, value: unknown) => void
  catalogNames: string[]
  onIconFileUploaded?: () => void
  /** Resolved product name (``Input.NAME``), never template tokens like ``NAME``. */
  packageBasenameForIcons: string
  readOnly?: boolean
}) {
  const getString = (key: string) => (pkginfo[key] as string) ?? ''
  const getBool = (key: string) => (pkginfo[key] as boolean) ?? false
  const getList = (key: string) => (pkginfo[key] as string[]) ?? []

  return (
    <div className="space-y-6">
      <div className="space-y-4">
        {PKGINFO_TEXT_FIELDS.map((field) => (
          <Fragment key={field.key}>
            <div className="space-y-2">
              <Label htmlFor={`pkg-${field.key}`}>{field.label}</Label>
              {field.multiline ? (
                <Textarea
                  id={`pkg-${field.key}`}
                  value={getString(field.key)}
                  readOnly={readOnly}
                  onChange={(e) =>
                    onUpdate(field.key, e.target.value || undefined)
                  }
                  rows={3}
                  className="text-sm"
                />
              ) : (
                <Input
                  id={`pkg-${field.key}`}
                  value={getString(field.key)}
                  readOnly={readOnly}
                  onChange={(e) =>
                    onUpdate(field.key, e.target.value || undefined)
                  }
                  className="text-sm"
                />
              )}
            </div>
            {field.key === 'name' && (
              <div className="space-y-2">
                <Label htmlFor="pkg-icon_name">Icon Name</Label>
                <p className="text-xs text-muted-foreground">
                  Filename stem without .png (Munki pkginfo).
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <Input
                    id="pkg-icon_name"
                    value={getString('icon_name')}
                    readOnly={readOnly}
                    onChange={(e) =>
                      onUpdate('icon_name', e.target.value || undefined)
                    }
                    className="max-w-md text-sm"
                    placeholder={
                      packageBasenameForIcons ||
                      'defaults to package name for upload'
                    }
                  />
                  <PkginfoIconUpload
                    suggestedBasename={packageBasenameForIcons}
                    currentIconName={getString('icon_name')}
                    disabled={readOnly}
                    onIconNameApplied={(v) => {
                      onUpdate('icon_name', v)
                      onIconFileUploaded?.()
                    }}
                  />
                </div>
              </div>
            )}
          </Fragment>
        ))}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {PKGINFO_BOOL_FIELDS.map((field) => (
          <div
            key={field.key}
            className="flex items-center gap-3 rounded-md border px-3 py-2"
          >
            <Switch
              id={`pkg-${field.key}`}
              checked={getBool(field.key)}
              onCheckedChange={(checked) => onUpdate(field.key, checked)}
              disabled={readOnly}
            />
            <Label htmlFor={`pkg-${field.key}`} className="cursor-pointer">
              {field.label}
            </Label>
          </div>
        ))}
      </div>

      {PKGINFO_LIST_FIELDS.map((field) => {
        const values = getList(field.key)
        const isThisCatalogs = field.key === 'catalogs'
        return (
          <div key={field.key} className="space-y-2">
            <Label>{field.label}</Label>
            {isThisCatalogs && catalogNames.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-1">
                {catalogNames.map((cat) => {
                  const selected = values.includes(cat)
                  return (
                    <Badge
                      key={cat}
                      variant={selected ? 'default' : 'outline'}
                      className={readOnly ? undefined : 'cursor-pointer'}
                      onClick={
                        readOnly
                          ? undefined
                          : () => {
                              const next = selected
                                ? values.filter((v) => v !== cat)
                                : [...values, cat]
                              onUpdate(
                                field.key,
                                next.length > 0 ? next : undefined,
                              )
                            }
                      }
                    >
                      {cat}
                    </Badge>
                  )
                })}
              </div>
            )}
            <Input
              value={values.join(', ')}
              readOnly={readOnly}
              onChange={(e) => {
                const next = parseCatalogListInput(e.target.value)
                onUpdate(field.key, next.length > 0 ? next : undefined)
              }}
              placeholder={
                isThisCatalogs
                  ? 'Comma, slash, or pipe — e.g. testing, dev, staging'
                  : `Comma-separated ${field.label.toLowerCase()}`
              }
              className="text-sm"
            />
          </div>
        )
      })}
    </div>
  )
}

// ── Main editor ──────────────────────────────────────────────────────────

export type RecipeOverrideToolbarApi = {
  save: () => void
  deleteRecipe: () => void
  isSaving: boolean
  isDeleting: boolean
  canSave: boolean
  isDirty: boolean
}

export function RecipeOverrideEditor({
  recipe,
  onDeleted,
  onSaved,
  readOnly = false,
  onToolbarApiChange,
  onRegisterDelete,
}: {
  recipe: AutoPkgRecipeRead
  onDeleted?: () => void
  onSaved?: () => void
  readOnly?: boolean
  /** When not read-only, exposes save/delete for a header toolbar (see recipe detail page). */
  onToolbarApiChange?: (api: RecipeOverrideToolbarApi | null) => void
  /** Exposes delete dialog opener even in read-only mode (detail page Delete button). */
  onRegisterDelete?: (openDelete: (() => void) | null) => void
}) {
  const queryClient = useQueryClient()
  const inputVarsRaw = recipe.input_variables as Record<string, unknown> | null
  const canonicalInput = recipeInputDict(recipe) ?? inputVarsRaw ?? {}
  const hasStoredOverridePlist = Boolean(recipe.override_data)

  const [identifier, setIdentifier] = useState(recipe.identifier)
  const [name, setName] = useState(recipe.name)
  const [parentRecipe, setParentRecipe] = useState(recipe.parent_recipe ?? '')
  const [sourceRepoFullName, setSourceRepoFullName] = useState(
    recipe.source_repo_full_name ?? '',
  )
  const [isEnabled, setIsEnabled] = useState(recipe.is_enabled)
  const [extractIconEnabled, setExtractIconEnabled] = useState(
    recipe.extract_icon_enabled ?? false,
  )
  const [autoPromote, setAutoPromote] = useState(recipe.auto_promote)
  const [promotionChannelId, setPromotionChannelId] = useState<string | null>(
    recipe.promotion_channel_id ?? null,
  )

  const [nonPkginfoEntries, setNonPkginfoEntries] = useState<KVEntry[]>(
    kvFromDict(extractNonPkginfoInput(canonicalInput)),
  )

  const initialPkginfo = extractPkginfo(canonicalInput)
  const [pkginfo, setPkginfo] =
    useState<Record<string, unknown>>(initialPkginfo)
  const [iconRevision, setIconRevision] = useState(0)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [baselineSnapshot, setBaselineSnapshot] = useState<string>('')

  useEffect(() => {
    const iv = recipe.input_variables as Record<string, unknown> | null
    const nextCanonical = recipeInputDict(recipe) ?? iv ?? {}
    setIdentifier(recipe.identifier)
    setName(recipe.name)
    setParentRecipe(recipe.parent_recipe ?? '')
    setSourceRepoFullName(recipe.source_repo_full_name ?? '')
    setIsEnabled(recipe.is_enabled)
    setExtractIconEnabled(recipe.extract_icon_enabled ?? false)
    setAutoPromote(recipe.auto_promote)
    setPromotionChannelId(recipe.promotion_channel_id ?? null)
    setNonPkginfoEntries(kvFromDict(extractNonPkginfoInput(nextCanonical)))
    setPkginfo(extractPkginfo(nextCanonical))
    // Dirty tracking baseline: capture a normalized snapshot of the recipe's
    // current persisted state so we can detect unsaved edits.
    const baselineNonPkg = extractNonPkginfoInput(nextCanonical)
    const baselinePkg = extractPkginfo(nextCanonical)
    const baselineHasPkg = Object.keys(baselinePkg).length > 0
    const baselineInput: Record<string, unknown> = {
      ...(baselineNonPkg ?? {}),
      ...(baselineHasPkg ? { pkginfo: baselinePkg } : {}),
    }
    const baselinePayload: Record<string, unknown> = {
      identifier: recipe.identifier,
      name: recipe.name,
      parent_recipe: recipe.parent_recipe ?? null,
      source_repo_full_name: recipe.source_repo_full_name ?? null,
      is_enabled: recipe.is_enabled,
      extract_icon_enabled: recipe.extract_icon_enabled ?? false,
      auto_promote: recipe.auto_promote,
      promotion_channel_id: recipe.promotion_channel_id ?? null,
      ...(hasStoredOverridePlist
        ? {
            override_data: {
              ...(((recipe.override_data as Record<string, unknown> | null) ??
                {}) as Record<string, unknown>),
              Identifier: recipe.identifier,
              ParentRecipe: recipe.parent_recipe ?? '',
              Input: baselineInput,
            },
            input_variables:
              baselineNonPkg && Object.keys(baselineNonPkg).length > 0
                ? baselineNonPkg
                : null,
          }
        : {
            input_variables:
              Object.keys(baselineInput).length > 0 ? baselineInput : null,
          }),
    }
    setBaselineSnapshot(JSON.stringify(baselinePayload))
  }, [recipe, hasStoredOverridePlist])

  const updatePkgField = (key: string, value: unknown) => {
    setPkginfo((prev) => ({ ...prev, [key]: value }))
  }

  const { data: catalogs } = useQuery({
    queryKey: ['catalogs'],
    queryFn: () => api.get<CatalogRead[]>('/catalogs'),
  })

  const { data: promotionChannels } = useQuery({
    queryKey: ['promotion-channels'],
    queryFn: () => api.get<PromotionChannelRead[]>('/promotion-channels'),
  })

  const {
    data: runnerPlistXml,
    isLoading: rawPlistLoading,
    isError: rawPlistError,
    error: rawPlistErr,
  } = useQuery({
    queryKey: ['autopkg-recipe-runner-plist', recipe.id],
    queryFn: () =>
      apiGetText(`/autopkg/recipes/${recipe.id}/runner-override.plist`),
  })

  const runnerPlistYaml = useMemo(() => {
    if (!runnerPlistXml) return ''
    try {
      const obj = plistParse(runnerPlistXml) as unknown
      return yaml.dump(obj, { lineWidth: 120, noRefs: true, sortKeys: true })
    } catch (e) {
      return `Could not convert to YAML: ${e instanceof Error ? e.message : String(e)}`
    }
  }, [runnerPlistXml])

  const yamlDownloadable =
    Boolean(runnerPlistYaml) &&
    !runnerPlistYaml.startsWith('Could not convert to YAML:')

  const downloadRunnerPlist = useCallback(async () => {
    try {
      const token =
        typeof window !== 'undefined' ? localStorage.getItem('token') : null
      const headers: Record<string, string> = {}
      if (token) headers.Authorization = `Bearer ${token}`
      const base = publicApiBaseUrl()
      const res = await fetch(
        `${base}/api/v1/autopkg/recipes/${recipe.id}/runner-override.plist`,
        { headers },
      )
      if (!res.ok) {
        const errBody = await res
          .json()
          .catch(() => ({ detail: res.statusText }))
        const d = errBody.detail
        const msg = typeof d === 'string' ? d : res.statusText
        throw new Error(msg || 'Download failed')
      }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const cd = res.headers.get('Content-Disposition')
      const m = cd?.match(/filename="([^"]+)"/)
      a.download =
        m?.[1] ?? `${recipe.name.replace(/[^\w.-]+/g, '_')}.recipe.plist`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      toast.error(
        e instanceof Error ? e.message : 'Failed to download runner override',
      )
    }
  }, [recipe.id, recipe.name])

  const downloadRunnerYaml = useCallback(() => {
    if (!yamlDownloadable) {
      toast.error('YAML is not available')
      return
    }
    const safe = recipe.name.replace(/[^\w.-]+/g, '_').replace(/^\.+|\.+$/g, '')
    const name = safe || 'override'
    const blob = new Blob([runnerPlistYaml], {
      type: 'text/yaml;charset=utf-8',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${name}.recipe.yaml`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }, [recipe.name, runnerPlistYaml, yamlDownloadable])

  const saveMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      api.put<AutoPkgRecipeRead>(`/autopkg/recipes/${recipe.id}`, payload),
    onSuccess: (updated) => {
      toast.success(`Recipe ${updated.name} updated`)
      queryClient.setQueryData(['autopkg-recipe', recipe.id], updated)
      queryClient.invalidateQueries({ queryKey: ['autopkg-recipes'] })
      queryClient.invalidateQueries({ queryKey: ['pkginfo-item-meta'] })
      queryClient.invalidateQueries({ queryKey: ['pkginfo-display-labels'] })
      queryClient.invalidateQueries({
        queryKey: ['autopkg-recipe-runner-plist', recipe.id],
      })
      queryClient.invalidateQueries({
        queryKey: ['audit', 'autopkg_recipe', recipe.id],
      })
      onSaved?.()
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`/autopkg/recipes/${recipe.id}`),
    onSuccess: () => {
      setDeleteDialogOpen(false)
      toast.success(`Recipe ${recipe.name} deleted`)
      queryClient.invalidateQueries({ queryKey: ['autopkg-recipes'] })
      queryClient.removeQueries({ queryKey: ['autopkg-recipe', recipe.id] })
      onDeleted?.()
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const updateTrustMutation = useMutation({
    mutationFn: () =>
      api.post<{ name: string; trust_status: string }>(
        `/autopkg/recipes/${recipe.id}/update-trust`,
      ),
    onSuccess: (data) => {
      toast.success(`Trust info updated for ${data.name}`)
      queryClient.invalidateQueries({ queryKey: ['autopkg-recipe', recipe.id] })
      queryClient.invalidateQueries({ queryKey: ['autopkg-recipes'] })
      queryClient.invalidateQueries({
        queryKey: ['autopkg-recipe-runner-plist', recipe.id],
      })
      queryClient.invalidateQueries({
        queryKey: ['pending-trust-changes-count'],
      })
      queryClient.invalidateQueries({ queryKey: ['pending-trust-changes'] })
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const handleSave = useCallback(() => {
    const nonPkgDict = kvToDict(nonPkginfoEntries)
    const hasPkginfo = Object.keys(pkginfo).length > 0
    const fullInput: Record<string, unknown> = {
      ...nonPkgDict,
      ...(hasPkginfo ? { pkginfo } : {}),
    }

    const payload: Record<string, unknown> = {
      identifier,
      name,
      parent_recipe: parentRecipe || null,
      source_repo_full_name: sourceRepoFullName.trim() || null,
      is_enabled: isEnabled,
      extract_icon_enabled: extractIconEnabled,
      auto_promote: autoPromote,
      promotion_channel_id: promotionChannelId,
    }

    if (hasStoredOverridePlist) {
      const prev =
        (recipe.override_data as Record<string, unknown> | null) ?? {}
      payload.override_data = {
        ...prev,
        Identifier: identifier,
        ParentRecipe: parentRecipe || '',
        Input: fullInput,
      }
      payload.input_variables =
        Object.keys(nonPkgDict).length > 0 ? nonPkgDict : null
    } else {
      payload.input_variables =
        Object.keys(fullInput).length > 0 ? fullInput : null
    }

    saveMutation.mutate(payload)
  }, [
    nonPkginfoEntries,
    pkginfo,
    identifier,
    name,
    parentRecipe,
    sourceRepoFullName,
    isEnabled,
    extractIconEnabled,
    autoPromote,
    promotionChannelId,
    hasStoredOverridePlist,
    recipe.override_data,
    saveMutation.mutate,
  ])

  const currentSnapshot = useMemo(() => {
    const nonPkgDict = kvToDict(nonPkginfoEntries)
    const hasPkginfo = Object.keys(pkginfo).length > 0
    const fullInput: Record<string, unknown> = {
      ...nonPkgDict,
      ...(hasPkginfo ? { pkginfo } : {}),
    }

    const payload: Record<string, unknown> = {
      identifier,
      name,
      parent_recipe: parentRecipe || null,
      source_repo_full_name: sourceRepoFullName.trim() || null,
      is_enabled: isEnabled,
      extract_icon_enabled: extractIconEnabled,
      auto_promote: autoPromote,
      promotion_channel_id: promotionChannelId,
    }

    if (hasStoredOverridePlist) {
      const prev =
        (recipe.override_data as Record<string, unknown> | null) ?? {}
      payload.override_data = {
        ...prev,
        Identifier: identifier,
        ParentRecipe: parentRecipe || '',
        Input: fullInput,
      }
      payload.input_variables =
        Object.keys(nonPkgDict).length > 0 ? nonPkgDict : null
    } else {
      payload.input_variables =
        Object.keys(fullInput).length > 0 ? fullInput : null
    }

    return JSON.stringify(payload)
  }, [
    nonPkginfoEntries,
    pkginfo,
    identifier,
    name,
    parentRecipe,
    sourceRepoFullName,
    isEnabled,
    extractIconEnabled,
    autoPromote,
    promotionChannelId,
    hasStoredOverridePlist,
    recipe.override_data,
  ])

  const isDirty =
    baselineSnapshot !== '' && currentSnapshot !== baselineSnapshot

  const openDeleteDialog = useCallback(() => {
    setDeleteDialogOpen(true)
  }, [])

  const confirmDeleteOverride = useCallback(() => {
    deleteMutation.mutate()
  }, [deleteMutation.mutate])

  useEffect(() => {
    if (readOnly) {
      onToolbarApiChange?.(null)
      return
    }
    onToolbarApiChange?.({
      save: handleSave,
      deleteRecipe: openDeleteDialog,
      isSaving: saveMutation.isPending,
      isDeleting: deleteMutation.isPending,
      canSave:
        Boolean(name.trim() && identifier.trim()) &&
        isDirty &&
        !saveMutation.isPending,
      isDirty,
    })
  }, [
    readOnly,
    onToolbarApiChange,
    handleSave,
    openDeleteDialog,
    saveMutation.isPending,
    deleteMutation.isPending,
    name,
    identifier,
    isDirty,
  ])

  useEffect(() => {
    if (!onRegisterDelete) return
    onRegisterDelete(openDeleteDialog)
    return () => onRegisterDelete(null)
  }, [onRegisterDelete, openDeleteDialog])

  const catalogNames = (catalogs ?? []).map((c) => c.name)
  const nonPkginfoCount = nonPkginfoEntries.length
  const pkginfoCount = Object.keys(pkginfo).length
  const iconUploadBasename = recipeIconUploadBasename(pkginfo, recipe)

  return (
    <>
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete override</DialogTitle>
            <DialogDescription>
              This will permanently delete{' '}
              <span className="font-medium text-foreground">{recipe.name}</span>{' '}
              and remove it from the recipe list. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:justify-between">
            <Button
              type="button"
              variant="outline"
              onClick={() => setDeleteDialogOpen(false)}
              disabled={deleteMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={confirmDeleteOverride}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? 'Deleting…' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Tabs defaultValue="general" className="gap-4">
        <TabsList
          className={cn(
            'h-auto w-full flex-wrap gap-2 rounded-xl p-2 sm:p-2.5',
            'border border-gruvbox-orange/20 bg-linear-to-br from-muted/90 via-muted/55 to-muted/25',
            'shadow-sm transition-[border-color,box-shadow] duration-300 ease-out',
            'hover:border-gruvbox-orange/40 hover:shadow-md dark:border-gruvbox-orange/30 dark:hover:border-gruvbox-orange/50',
          )}
        >
          <TabsTrigger
            value="general"
            className={recipeDetailTabTrigger(
              'data-[state=active]:text-gruvbox-blue data-[state=active]:ring-2 data-[state=active]:ring-gruvbox-blue/30',
            )}
          >
            <FileText className={recipeTabIconClass} aria-hidden />
            General
          </TabsTrigger>
          <TabsTrigger
            value="input"
            className={recipeDetailTabTrigger(
              'data-[state=active]:text-gruvbox-purple data-[state=active]:ring-2 data-[state=active]:ring-gruvbox-purple/30',
            )}
          >
            <Braces className={recipeTabIconClass} aria-hidden />
            Input
            {nonPkginfoCount > 0 && (
              <Badge variant="secondary" className="ml-1.5 text-xs px-1.5">
                {nonPkginfoCount}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger
            value="pkginfo"
            className={recipeDetailTabTrigger(
              'data-[state=active]:text-gruvbox-green data-[state=active]:ring-2 data-[state=active]:ring-gruvbox-green/30',
            )}
          >
            <Package className={recipeTabIconClass} aria-hidden />
            pkginfo
            {pkginfoCount > 0 && (
              <Badge variant="secondary" className="ml-1.5 text-xs px-1.5">
                {pkginfoCount}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger
            value="trust"
            className={recipeDetailTabTrigger(
              'data-[state=active]:text-gruvbox-yellow data-[state=active]:ring-2 data-[state=active]:ring-gruvbox-yellow/35',
            )}
          >
            <ShieldCheck className={recipeTabIconClass} aria-hidden />
            Trust Info
          </TabsTrigger>
          <TabsTrigger
            value="raw-xml"
            className={recipeDetailTabTrigger(
              'data-[state=active]:text-sky-500 data-[state=active]:ring-2 data-[state=active]:ring-sky-500/30',
            )}
          >
            <FileCode2 className={recipeTabIconClass} aria-hidden />
            xml
          </TabsTrigger>
          <TabsTrigger
            value="raw-yaml"
            className={recipeDetailTabTrigger(
              'data-[state=active]:text-emerald-500 data-[state=active]:ring-2 data-[state=active]:ring-emerald-500/30',
            )}
          >
            <ListTree className={recipeTabIconClass} aria-hidden />
            yaml
          </TabsTrigger>
          <TabsTrigger
            value="audit"
            className={recipeDetailTabTrigger(
              'data-[state=active]:text-gruvbox-red data-[state=active]:ring-2 data-[state=active]:ring-gruvbox-red/30',
            )}
          >
            <History className={recipeTabIconClass} aria-hidden />
            Audit Trail
          </TabsTrigger>
        </TabsList>

        <TabsContent value="general" className={recipeDetailTabContentClass}>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="recipe-name">Name</Label>
              <Input
                id="recipe-name"
                value={name}
                readOnly={readOnly}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="recipe-identifier">Identifier</Label>
              <Input
                id="recipe-identifier"
                value={identifier}
                readOnly={readOnly}
                onChange={(e) => setIdentifier(e.target.value)}
                className="font-mono text-sm"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="recipe-parent">Parent Recipe</Label>
            <Input
              id="recipe-parent"
              value={parentRecipe}
              readOnly={readOnly}
              onChange={(e) => setParentRecipe(e.target.value)}
              placeholder="com.github.autopkg.munki.Firefox"
              className="font-mono text-sm"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="recipe-source-repo">Source repo (GitHub)</Label>
            <Input
              id="recipe-source-repo"
              value={sourceRepoFullName}
              readOnly={readOnly}
              onChange={(e) => setSourceRepoFullName(e.target.value)}
              placeholder="autopkg/recipes"
              className="font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground">
              Used for runner repo-add hints and inferred repo lists
              (owner/repo, no URL).
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex items-center gap-3 rounded-md border px-3 py-2">
              <Switch
                id="recipe-enabled"
                checked={isEnabled}
                onCheckedChange={setIsEnabled}
                disabled={readOnly}
              />
              <Label htmlFor="recipe-enabled" className="cursor-pointer">
                Enabled
              </Label>
            </div>
            <div className="flex items-center gap-3 rounded-md border px-3 py-2">
              <Switch
                id="recipe-auto-promote"
                checked={autoPromote}
                onCheckedChange={setAutoPromote}
                disabled={readOnly}
              />
              <Label htmlFor="recipe-auto-promote" className="cursor-pointer">
                Auto Promote
              </Label>
            </div>
          </div>

          <div className="flex items-start gap-3 rounded-md border px-3 py-2">
            <Switch
              id="recipe-extract-icon"
              checked={extractIconEnabled}
              onCheckedChange={setExtractIconEnabled}
              disabled={readOnly}
            />
            <div>
              <Label htmlFor="recipe-extract-icon" className="cursor-pointer">
                Extract icon (MunkiImporter)
              </Label>
              <p className="text-xs text-muted-foreground mt-0.5">
                On the next run, copy an app icon from the installer into the
                local Munki repo and upload it to the app. Requires Munki tools
                on the runner.
              </p>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="recipe-promotion-channel">Promotion channel</Label>
            <p className="text-xs text-muted-foreground">
              Timed catalog steps after import (see Approvals). Use workflow
              default or pick a channel for this recipe.
            </p>
            <Select
              value={promotionChannelId ?? '__default__'}
              onValueChange={(v) =>
                setPromotionChannelId(v === '__default__' ? null : v)
              }
              disabled={readOnly}
            >
              <SelectTrigger
                id="recipe-promotion-channel"
                className="w-full max-w-md"
              >
                <SelectValue placeholder="Workflow default" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__default__">Workflow default</SelectItem>
                {(promotionChannels ?? []).map((ch) => (
                  <SelectItem key={ch.id} value={ch.id}>
                    {ch.name}
                    {ch.steps.length
                      ? ` (${ch.steps.length} step${ch.steps.length === 1 ? '' : 's'})`
                      : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="recipe-catalogs">Catalogs</Label>
            <p className="text-xs text-muted-foreground">
              Stored as{' '}
              <span className="font-mono">Input.pkginfo.catalogs</span> (what
              AutoPkg writes into pkginfo).
            </p>
            <div className="flex flex-wrap gap-1 mb-2">
              {catalogNames.map((cat) => {
                const values = Array.isArray(pkginfo.catalogs)
                  ? (pkginfo.catalogs as string[]).filter(
                      (x): x is string => typeof x === 'string',
                    )
                  : []
                const selected = values.includes(cat)
                return (
                  <Badge
                    key={cat}
                    variant={selected ? 'default' : 'outline'}
                    className={readOnly ? undefined : 'cursor-pointer'}
                    onClick={
                      readOnly
                        ? undefined
                        : () => {
                            const next = selected
                              ? values.filter((c) => c !== cat)
                              : [...values, cat]
                            updatePkgField(
                              'catalogs',
                              next.length > 0 ? next : undefined,
                            )
                          }
                    }
                  >
                    {cat}
                  </Badge>
                )
              })}
            </div>
            <Input
              id="recipe-catalogs"
              value={
                Array.isArray(pkginfo.catalogs)
                  ? (pkginfo.catalogs as string[]).join(', ')
                  : ''
              }
              readOnly={readOnly}
              onChange={(e) => {
                const next = parseCatalogListInput(e.target.value)
                updatePkgField('catalogs', next.length > 0 ? next : undefined)
              }}
              placeholder="testing, dev, staging or testing/dev/staging"
            />
          </div>

          <div className="space-y-2 rounded-md border p-4">
            <Label>Software icon</Label>
            <p className="text-xs text-muted-foreground">
              PNG stored in the database and served at{' '}
              <span className="font-mono">/icons/*.png</span> to the UI and{' '}
              <span className="font-mono">/repo/icons/*.png</span> to Munki
              clients. Uses Icon Name from pkginfo if set, otherwise Package
              Name.
            </p>
            <div className="flex flex-wrap items-center gap-4">
              <SoftwareIcon
                name={iconUploadBasename}
                displayName={
                  typeof pkginfo.display_name === 'string'
                    ? pkginfo.display_name
                    : null
                }
                iconName={
                  typeof pkginfo.icon_name === 'string'
                    ? pkginfo.icon_name
                    : null
                }
                size="md"
                cacheRevision={iconRevision}
              />
              <PkginfoIconUpload
                suggestedBasename={iconUploadBasename}
                currentIconName={
                  typeof pkginfo.icon_name === 'string' ? pkginfo.icon_name : ''
                }
                disabled={readOnly}
                onIconNameApplied={(v) => {
                  updatePkgField('icon_name', v)
                  setIconRevision((r) => r + 1)
                }}
              />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="input" className={recipeDetailTabContentClass}>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Input Variables</Label>
              <span className="text-xs text-muted-foreground">
                Non-pkginfo keys (e.g. NAME, MUNKI_REPO_SUBDIR)
              </span>
            </div>
            <KeyValueEditor
              entries={nonPkginfoEntries}
              onChange={setNonPkginfoEntries}
              keyPlaceholder="VARIABLE_NAME"
              valuePlaceholder="value"
              readOnly={readOnly}
            />
          </div>
        </TabsContent>

        <TabsContent value="pkginfo" className={recipeDetailTabContentClass}>
          <PkginfoEditor
            pkginfo={pkginfo}
            onUpdate={updatePkgField}
            catalogNames={catalogNames}
            packageBasenameForIcons={iconUploadBasename}
            onIconFileUploaded={() => setIconRevision((r) => r + 1)}
            readOnly={readOnly}
          />
        </TabsContent>

        <TabsContent value="trust" className={recipeDetailTabContentClass}>
          <TrustInfoViewer
            trustInfo={recipe.trust_info as Record<string, unknown> | null}
          />
          {recipe.parent_recipe && !readOnly && (
            <div className="mt-4 pt-4 border-t">
              <Button
                variant="outline"
                size="sm"
                disabled={updateTrustMutation.isPending}
                onClick={() => updateTrustMutation.mutate()}
              >
                {updateTrustMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="mr-2 h-4 w-4" />
                )}
                Re-fetch Trust Info from GitHub
              </Button>
              <p className="mt-1 text-xs text-muted-foreground">
                Re-resolves all parent recipes and updates stored hashes and
                locations.
              </p>
            </div>
          )}
        </TabsContent>

        <TabsContent value="raw-xml" className={recipeDetailTabContentClass}>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-muted-foreground sm:pr-2">
              Override plist in XML form (same file AutoPkg runners use).
              Read-only.
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="shrink-0"
              aria-label="Download override plist (XML)"
              disabled={rawPlistLoading || rawPlistError}
              onClick={() => {
                void downloadRunnerPlist()
              }}
            >
              <Download className="mr-1.5 h-4 w-4" aria-hidden />
              Download
            </Button>
          </div>
          {rawPlistLoading ? (
            <div
              className="raw-data-viewport flex items-center justify-center gap-2 rounded-md border text-muted-foreground"
              role="status"
            >
              <Loader2 className="h-5 w-5 animate-spin" aria-hidden />
              Loading…
            </div>
          ) : rawPlistError ? (
            <p className="text-sm text-destructive">
              {rawPlistErr instanceof Error
                ? rawPlistErr.message
                : 'Failed to load plist'}
            </p>
          ) : (
            <ScrollArea
              className="raw-data-viewport rounded-md border bg-muted/30"
              data-slot="raw-xml-scroll"
            >
              <pre className="m-0 min-w-min max-w-full overflow-x-auto p-4 text-xs font-mono whitespace-pre">
                {runnerPlistXml}
              </pre>
            </ScrollArea>
          )}
        </TabsContent>

        <TabsContent value="raw-yaml" className={recipeDetailTabContentClass}>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-muted-foreground sm:pr-2">
              Same override data as YAML (parsed from the XML plist) for easy
              reading. Read-only.
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="shrink-0"
              aria-label="Download override as YAML"
              disabled={rawPlistLoading || rawPlistError || !yamlDownloadable}
              onClick={downloadRunnerYaml}
            >
              <Download className="mr-1.5 h-4 w-4" aria-hidden />
              Download
            </Button>
          </div>
          {rawPlistLoading ? (
            <div
              className="raw-data-viewport flex items-center justify-center gap-2 rounded-md border text-muted-foreground"
              role="status"
            >
              <Loader2 className="h-5 w-5 animate-spin" aria-hidden />
              Loading…
            </div>
          ) : rawPlistError ? (
            <p className="text-sm text-destructive">
              {rawPlistErr instanceof Error
                ? rawPlistErr.message
                : 'Failed to load plist'}
            </p>
          ) : (
            <ScrollArea
              className="raw-data-viewport rounded-md border bg-muted/30"
              data-slot="raw-yaml-scroll"
            >
              <pre className="m-0 max-w-full overflow-x-auto p-4 text-xs font-mono whitespace-pre-wrap wrap-break-word">
                {runnerPlistYaml}
              </pre>
            </ScrollArea>
          )}
        </TabsContent>

        <TabsContent value="audit" className={recipeDetailTabContentClass}>
          <EntityAuditTrail entityType="autopkg_recipe" entityId={recipe.id} />
        </TabsContent>
      </Tabs>
    </>
  )
}
