import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { api, type CatalogRead } from '@/lib/api'
import { parseCatalogListInput } from '@/lib/autopkg-recipe'
import { cn } from '@/lib/utils'

function catalogNameSetsEqual(a: string[], b: string[]): boolean {
  if (a.length !== b.length) {
    return false
  }
  const sa = [...a]
    .map((s) => s.trim())
    .filter(Boolean)
    .sort()
  const sb = [...b]
    .map((s) => s.trim())
    .filter(Boolean)
    .sort()
  for (let i = 0; i < sa.length; i++) {
    if (sa[i] !== sb[i]) {
      return false
    }
  }
  return true
}

export function CatalogEditor({
  pkgId,
  catalogNames,
  readOnly = false,
}: {
  pkgId: string
  catalogNames: string[]
  readOnly?: boolean
}) {
  const queryClient = useQueryClient()
  const [inputText, setInputText] = useState(() => catalogNames.join(', '))

  useEffect(() => {
    setInputText(catalogNames.join(', '))
  }, [catalogNames])

  const { data: allCatalogs = [] } = useQuery({
    queryKey: ['catalogs'],
    queryFn: () => api.get<CatalogRead[]>('/catalogs'),
  })

  const sorted = useMemo(
    () => [...allCatalogs].sort((a, b) => a.name.localeCompare(b.name)),
    [allCatalogs],
  )

  const unknownSelected = useMemo(
    () => catalogNames.filter((n) => !allCatalogs.some((c) => c.name === n)),
    [catalogNames, allCatalogs],
  )

  const mutation = useMutation({
    mutationFn: (names: string[]) =>
      api.put(`/pkginfo/${pkgId}/catalogs`, { catalog_names: names }),
    onSuccess: () => {
      toast.success('Catalogs updated')
      queryClient.invalidateQueries({ queryKey: ['pkginfo', pkgId] })
      queryClient.invalidateQueries({ queryKey: ['catalogs'] })
    },
    onError: (err: Error) =>
      toast.error(`Failed to update catalogs: ${err.message}`),
  })

  const pending = mutation.isPending

  const toggle = (name: string) => {
    if (readOnly) {
      return
    }
    const next = catalogNames.includes(name)
      ? catalogNames.filter((c) => c !== name)
      : [...catalogNames, name]
    mutation.mutate(next)
  }

  const applyInput = () => {
    if (readOnly) {
      return
    }
    const next = parseCatalogListInput(inputText)
    if (catalogNameSetsEqual(next, catalogNames)) {
      setInputText(catalogNames.join(', '))
    } else {
      mutation.mutate(next)
    }
  }

  return (
    <div className="space-y-2">
      {sorted.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1">
          {sorted.map((cat) => {
            const selected = catalogNames.includes(cat.name)
            return (
              <Badge
                key={cat.id}
                variant={selected ? 'default' : 'outline'}
                className={cn(
                  'text-sm',
                  readOnly || pending ? undefined : 'cursor-pointer',
                  pending && 'pointer-events-none opacity-60',
                )}
                onClick={
                  readOnly || pending ? undefined : () => toggle(cat.name)
                }
              >
                {cat.name}
              </Badge>
            )
          })}
        </div>
      )}
      {unknownSelected.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs text-muted-foreground">
            In pkginfo but not in the server catalog list (click to remove when
            editing)
          </p>
          <div className="mb-2 flex flex-wrap gap-1">
            {unknownSelected.map((name) => (
              <Badge
                key={name}
                variant="default"
                className={cn(
                  'text-sm',
                  readOnly || pending ? undefined : 'cursor-pointer',
                  pending && 'pointer-events-none opacity-60',
                )}
                onClick={readOnly || pending ? undefined : () => toggle(name)}
              >
                {name}
              </Badge>
            ))}
          </div>
        </div>
      )}
      <Input
        id="pkginfo-catalogs-input"
        value={inputText}
        readOnly={readOnly}
        disabled={pending}
        onChange={
          readOnly
            ? undefined
            : (e) => {
                setInputText(e.target.value)
              }
        }
        onBlur={readOnly ? undefined : applyInput}
        onKeyDown={
          readOnly
            ? undefined
            : (e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  ;(e.currentTarget as HTMLInputElement).blur()
                }
              }
        }
        placeholder="testing, dev, staging or testing/dev/staging"
        className="text-sm"
      />
    </div>
  )
}
