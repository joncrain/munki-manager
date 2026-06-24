import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { api, type CatalogRead } from '@/lib/api'
import { parseCatalogListInput } from '@/lib/autopkg-recipe'
import { catalogNameSetsEqual } from '@/lib/catalog-names'
import { cn } from '@/lib/utils'

export function CatalogEditor({
  catalogNames,
  onChange,
  readOnly = false,
}: {
  catalogNames: string[]
  onChange: (names: string[]) => void
  readOnly?: boolean
}) {
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

  const toggle = (name: string) => {
    if (readOnly) {
      return
    }
    const next = catalogNames.includes(name)
      ? catalogNames.filter((c) => c !== name)
      : [...catalogNames, name]
    onChange(next)
  }

  const applyInput = () => {
    if (readOnly) {
      return
    }
    const next = parseCatalogListInput(inputText)
    if (catalogNameSetsEqual(next, catalogNames)) {
      setInputText(catalogNames.join(', '))
    } else {
      onChange(next)
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
                  readOnly ? undefined : 'cursor-pointer',
                )}
                onClick={readOnly ? undefined : () => toggle(cat.name)}
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
            In pkginfo but not in the server catalog list
            {readOnly ? '' : ' (click to remove when editing)'}
          </p>
          <div className="mb-2 flex flex-wrap gap-1">
            {unknownSelected.map((name) => (
              <Badge
                key={name}
                variant="default"
                className={cn(
                  'text-sm',
                  readOnly ? undefined : 'cursor-pointer',
                )}
                onClick={readOnly ? undefined : () => toggle(name)}
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
