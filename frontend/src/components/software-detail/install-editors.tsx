import { Plus, Trash2 } from 'lucide-react'
import { useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import type { InstallItem, ItemToCopy, ReceiptItem } from '@/lib/api'

const INSTALL_TYPES = [
  'file',
  'bundle',
  'plist',
  'application',
  'launchd',
  'startup_item',
]

function rowKey(parts: unknown[]): string {
  return parts.map((p) => String(p ?? '')).join('\0')
}

export function installItemKey(item: InstallItem): string {
  return rowKey([
    item.type,
    item.path,
    item.CFBundleIdentifier,
    item.CFBundleShortVersionString,
    item.version_comparison_key,
    item.minosversion,
  ])
}

export function receiptItemKey(item: ReceiptItem): string {
  return rowKey([item.packageid, item.version, item.optional])
}

export function itemToCopyKey(item: ItemToCopy): string {
  return rowKey([
    item.source_item,
    item.destination_path,
    item.destination_item,
    item.user,
    item.group,
    item.mode,
  ])
}

function useEditableRowKeys(length: number) {
  const keysRef = useRef<string[]>([])

  while (keysRef.current.length < length) {
    keysRef.current.push(crypto.randomUUID())
  }
  keysRef.current.length = length

  const removeKeyAt = (index: number) => {
    keysRef.current.splice(index, 1)
  }
  const appendKey = () => {
    keysRef.current.push(crypto.randomUUID())
  }

  return { keys: keysRef.current, removeKeyAt, appendKey }
}

export function InstallsEditor({
  items,
  onChange,
}: {
  items: InstallItem[]
  onChange: (items: InstallItem[]) => void
}) {
  const { keys, removeKeyAt, appendKey } = useEditableRowKeys(items.length)

  const updateItem = (index: number, field: string, value: string) => {
    const updated = [...items]
    updated[index] = { ...updated[index], [field]: value }
    onChange(updated)
  }

  const removeItem = (index: number) => {
    removeKeyAt(index)
    onChange(items.filter((_, i) => i !== index))
  }

  const addItem = () => {
    appendKey()
    onChange([...items, { type: 'file', path: '' }])
  }

  return (
    <div className="space-y-3">
      {items.map((item, i) => (
        <div key={keys[i]} className="rounded-md border p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-medium">Item {i + 1}</span>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-destructive"
              onClick={() => removeItem(i)}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            <div>
              <Label className="text-xs">Type</Label>
              <Select
                value={item.type ?? 'file'}
                onValueChange={(v) => updateItem(i, 'type', v)}
              >
                <SelectTrigger className="mt-1 h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {INSTALL_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Path</Label>
              <Input
                className="mt-1 h-8 text-xs"
                value={item.path ?? ''}
                onChange={(e) => updateItem(i, 'path', e.target.value)}
                placeholder="/Applications/Example.app"
              />
            </div>
            <div>
              <Label className="text-xs">CFBundleIdentifier</Label>
              <Input
                className="mt-1 h-8 text-xs"
                value={(item.CFBundleIdentifier as string) ?? ''}
                onChange={(e) =>
                  updateItem(i, 'CFBundleIdentifier', e.target.value)
                }
                placeholder="com.example.app"
              />
            </div>
            <div>
              <Label className="text-xs">CFBundleShortVersionString</Label>
              <Input
                className="mt-1 h-8 text-xs"
                value={(item.CFBundleShortVersionString as string) ?? ''}
                onChange={(e) =>
                  updateItem(i, 'CFBundleShortVersionString', e.target.value)
                }
                placeholder="1.0.0"
              />
            </div>
            <div>
              <Label className="text-xs">version_comparison_key</Label>
              <Input
                className="mt-1 h-8 text-xs"
                value={(item.version_comparison_key as string) ?? ''}
                onChange={(e) =>
                  updateItem(i, 'version_comparison_key', e.target.value)
                }
                placeholder="CFBundleShortVersionString"
              />
            </div>
            <div>
              <Label className="text-xs">minosversion</Label>
              <Input
                className="mt-1 h-8 text-xs"
                value={(item.minosversion as string) ?? ''}
                onChange={(e) => updateItem(i, 'minosversion', e.target.value)}
                placeholder="10.15"
              />
            </div>
          </div>
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={addItem}>
        <Plus className="mr-1 h-3.5 w-3.5" />
        Add Install Item
      </Button>
    </div>
  )
}

export function ReceiptsEditor({
  items,
  onChange,
}: {
  items: ReceiptItem[]
  onChange: (items: ReceiptItem[]) => void
}) {
  const { keys, removeKeyAt, appendKey } = useEditableRowKeys(items.length)

  const updateItem = (
    index: number,
    field: string,
    value: string | boolean,
  ) => {
    const updated = [...items]
    updated[index] = { ...updated[index], [field]: value }
    onChange(updated)
  }

  const removeItem = (index: number) => {
    removeKeyAt(index)
    onChange(items.filter((_, i) => i !== index))
  }

  const addItem = () => {
    appendKey()
    onChange([...items, { packageid: '', version: '' }])
  }

  return (
    <div className="space-y-3">
      {items.map((item, i) => (
        <div key={keys[i]} className="rounded-md border p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-medium">Receipt {i + 1}</span>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-destructive"
              onClick={() => removeItem(i)}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
          <div className="grid gap-2 md:grid-cols-3">
            <div>
              <Label className="text-xs">Package ID</Label>
              <Input
                className="mt-1 h-8 text-xs"
                value={item.packageid ?? ''}
                onChange={(e) => updateItem(i, 'packageid', e.target.value)}
                placeholder="com.example.pkg"
              />
            </div>
            <div>
              <Label className="text-xs">Version</Label>
              <Input
                className="mt-1 h-8 text-xs"
                value={item.version ?? ''}
                onChange={(e) => updateItem(i, 'version', e.target.value)}
                placeholder="1.0.0"
              />
            </div>
            <div className="flex items-end gap-2 pb-0.5">
              <div className="flex items-center gap-2">
                <Switch
                  checked={item.optional ?? false}
                  onCheckedChange={(v) => updateItem(i, 'optional', v)}
                />
                <Label className="text-xs">Optional</Label>
              </div>
            </div>
          </div>
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={addItem}>
        <Plus className="mr-1 h-3.5 w-3.5" />
        Add Receipt
      </Button>
    </div>
  )
}

export function ItemsToCopyEditor({
  items,
  onChange,
}: {
  items: ItemToCopy[]
  onChange: (items: ItemToCopy[]) => void
}) {
  const { keys, removeKeyAt, appendKey } = useEditableRowKeys(items.length)

  const updateItem = (index: number, field: string, value: string) => {
    const updated = [...items]
    updated[index] = { ...updated[index], [field]: value }
    onChange(updated)
  }

  const removeItem = (index: number) => {
    removeKeyAt(index)
    onChange(items.filter((_, i) => i !== index))
  }

  const addItem = () => {
    appendKey()
    onChange([...items, { source_item: '', destination_path: '' }])
  }

  return (
    <div className="space-y-3">
      {items.map((item, i) => (
        <div key={keys[i]} className="rounded-md border p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-medium">Item {i + 1}</span>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-destructive"
              onClick={() => removeItem(i)}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            <div>
              <Label className="text-xs">Source Item</Label>
              <Input
                className="mt-1 h-8 text-xs"
                value={item.source_item ?? ''}
                onChange={(e) => updateItem(i, 'source_item', e.target.value)}
                placeholder="Example.app"
              />
            </div>
            <div>
              <Label className="text-xs">Destination Path</Label>
              <Input
                className="mt-1 h-8 text-xs"
                value={item.destination_path ?? ''}
                onChange={(e) =>
                  updateItem(i, 'destination_path', e.target.value)
                }
                placeholder="/Applications"
              />
            </div>
            <div>
              <Label className="text-xs">Destination Item</Label>
              <Input
                className="mt-1 h-8 text-xs"
                value={item.destination_item ?? ''}
                onChange={(e) =>
                  updateItem(i, 'destination_item', e.target.value)
                }
              />
            </div>
            <div>
              <Label className="text-xs">User</Label>
              <Input
                className="mt-1 h-8 text-xs"
                value={item.user ?? ''}
                onChange={(e) => updateItem(i, 'user', e.target.value)}
                placeholder="root"
              />
            </div>
            <div>
              <Label className="text-xs">Group</Label>
              <Input
                className="mt-1 h-8 text-xs"
                value={item.group ?? ''}
                onChange={(e) => updateItem(i, 'group', e.target.value)}
                placeholder="admin"
              />
            </div>
            <div>
              <Label className="text-xs">Mode</Label>
              <Input
                className="mt-1 h-8 text-xs"
                value={item.mode ?? ''}
                onChange={(e) => updateItem(i, 'mode', e.target.value)}
                placeholder="o-w"
              />
            </div>
          </div>
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={addItem}>
        <Plus className="mr-1 h-3.5 w-3.5" />
        Add Item to Copy
      </Button>
    </div>
  )
}
