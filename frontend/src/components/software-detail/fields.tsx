import { X } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'

export function ReadOnlyField({
  label,
  value,
}: {
  label: string
  value: ReactNode
}) {
  return (
    <div>
      <span className="text-sm font-medium text-muted-foreground">{label}</span>
      <div className="mt-1 truncate">{value || '—'}</div>
    </div>
  )
}

export function EditableField({
  label,
  value,
  editing,
  onChange,
}: {
  label: string
  value: string
  editing: boolean
  onChange: (v: string) => void
}) {
  if (!editing) {
    return (
      <div>
        <span className="text-sm font-medium text-muted-foreground">
          {label}
        </span>
        <p className="mt-1 truncate">{value || '—'}</p>
      </div>
    )
  }
  return (
    <div>
      <Label>{label}</Label>
      <Input
        className="mt-1"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}

/** Munki ``installer_item_size`` is in KiB; we edit in MB for readability. */
export function InstallerSizeMbField({
  label,
  kb,
  editing,
  onKbChange,
}: {
  label: string
  kb: number | null | undefined
  editing: boolean
  onKbChange: (v: number | null) => void
}) {
  const displayMb = kb != null && kb > 0 ? `${Math.round(kb / 1024)} MB` : '—'
  if (!editing) {
    return (
      <div>
        <span className="text-sm font-medium text-muted-foreground">
          {label}
        </span>
        <p className="mt-1 truncate">{displayMb}</p>
      </div>
    )
  }
  return (
    <div>
      <Label>{label} (MB)</Label>
      <Input
        type="number"
        min={0}
        className="mt-1"
        value={kb != null && kb > 0 ? Math.round(kb / 1024) : ''}
        onChange={(e) => {
          const v = e.target.value
          if (v === '') onKbChange(null)
          else {
            const n = Number.parseInt(v, 10)
            if (!Number.isNaN(n)) onKbChange(n * 1024)
          }
        }}
      />
      <p className="mt-1 text-xs text-muted-foreground">
        Stored as KiB for Munki installer_item_size.
      </p>
    </div>
  )
}

export function BooleanField({
  label,
  value,
  editing,
  onChange,
}: {
  label: string
  value: boolean
  editing: boolean
  onChange: (v: boolean) => void
}) {
  if (!editing) {
    return (
      <div>
        <span className="text-sm font-medium text-muted-foreground">
          {label}
        </span>
        <p className="mt-1">
          <Badge variant={value ? 'default' : 'outline'}>
            {value ? 'Yes' : 'No'}
          </Badge>
        </p>
      </div>
    )
  }
  return (
    <div className="flex items-center justify-between">
      <Label>{label}</Label>
      <Switch checked={value} onCheckedChange={onChange} />
    </div>
  )
}

export function TagField({
  label,
  values,
  onChange,
}: {
  label: string
  values: string[]
  onChange: (v: string[]) => void
}) {
  const [input, setInput] = useState('')

  const addTag = () => {
    const trimmed = input.trim()
    if (trimmed && !values.includes(trimmed)) {
      onChange([...values, trimmed])
    }
    setInput('')
  }

  return (
    <div>
      <Label>{label}</Label>
      <div className="mt-1 flex flex-wrap gap-1">
        {values.map((v) => (
          <Badge key={v} variant="secondary" className="gap-1">
            {v}
            <button
              type="button"
              aria-label={`Remove ${v}`}
              className="ml-1 hover:text-destructive"
              onClick={() => onChange(values.filter((x) => x !== v))}
            >
              <X className="h-3 w-3" />
            </button>
          </Badge>
        ))}
      </div>
      <div className="mt-2 flex gap-2">
        <Input
          placeholder={`Add ${label.toLowerCase()}...`}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              addTag()
            }
          }}
          className="max-w-xs"
        />
        <Button type="button" variant="outline" size="sm" onClick={addTag}>
          Add
        </Button>
      </div>
    </div>
  )
}

export function TagDisplay({
  label,
  values,
}: {
  label: string
  values: string[] | null | undefined
}) {
  if (!values?.length) {
    return (
      <div>
        <span className="text-sm font-medium text-muted-foreground">
          {label}
        </span>
        <p className="mt-1 text-sm text-muted-foreground">—</p>
      </div>
    )
  }
  return (
    <div>
      <span className="text-sm font-medium text-muted-foreground">{label}</span>
      <div className="mt-1 flex flex-wrap gap-1">
        {values.map((v) => (
          <Badge key={v} variant="outline">
            {v}
          </Badge>
        ))}
      </div>
    </div>
  )
}

export function ScriptField({
  label,
  value,
  editing,
  onChange,
  description,
}: {
  label: string
  value: string
  editing: boolean
  onChange: (v: string) => void
  description?: string
}) {
  if (!editing && !value) return null
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{label}</CardTitle>
        {description && (
          <p className="text-sm text-muted-foreground">{description}</p>
        )}
      </CardHeader>
      <CardContent>
        {editing ? (
          <Textarea
            className="min-h-[120px] font-mono text-sm"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={`Enter ${label}...`}
            rows={8}
          />
        ) : (
          <pre className="overflow-auto rounded-md bg-muted p-4 font-mono text-sm">
            {value}
          </pre>
        )}
      </CardContent>
    </Card>
  )
}
