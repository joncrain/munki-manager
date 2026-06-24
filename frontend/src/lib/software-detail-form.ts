import type {
  InstallItem,
  ItemToCopy,
  PkgInfoDetail,
  ReceiptItem,
} from '@/lib/api'

export interface EditableFields {
  display_name: string
  description: string
  category: string
  developer: string
  icon_name: string
  installer_item_location: string
  installer_item_hash: string
  installer_item_size: number | null
  minimum_os_version: string
  maximum_os_version: string
  uninstall_method: string
  unattended_install: boolean
  unattended_uninstall: boolean
  autoremove: boolean
  uninstallable: boolean
  blocking_applications: string[]
  supported_architectures: string[]
  requires: string[]
  update_for: string[]
  installs: InstallItem[]
  receipts: ReceiptItem[]
  items_to_copy: ItemToCopy[]
  installcheck_script: string
  uninstallcheck_script: string
  version_script: string
  preinstall_script: string
  postinstall_script: string
  preuninstall_script: string
  postuninstall_script: string
  notes: string
  restart_action: string
  on_demand: boolean
  force_install_after_date: string
  apple_item: boolean
  installable_condition: string
  package_path: string
  package_complete_url: string
  minimum_munki_version: string
  installer_type: string
  installed_size: number | null
  uninstaller_item_location: string
}

export function pkgToEditable(pkg: PkgInfoDetail): EditableFields {
  return {
    display_name: pkg.display_name ?? '',
    description: pkg.description ?? '',
    category: pkg.category ?? '',
    developer: pkg.developer ?? '',
    icon_name: pkg.icon_name ?? '',
    installer_item_location: pkg.installer_item_location ?? '',
    installer_item_hash: pkg.installer_item_hash ?? '',
    installer_item_size: pkg.installer_item_size,
    minimum_os_version: pkg.minimum_os_version ?? '',
    maximum_os_version: pkg.maximum_os_version ?? '',
    uninstall_method: pkg.uninstall_method ?? '',
    unattended_install: pkg.unattended_install,
    unattended_uninstall: pkg.unattended_uninstall,
    autoremove: pkg.autoremove,
    uninstallable: pkg.uninstallable,
    blocking_applications: pkg.blocking_applications ?? [],
    supported_architectures: pkg.supported_architectures ?? [],
    requires: pkg.requires ?? [],
    update_for: pkg.update_for ?? [],
    installs: pkg.installs ?? [],
    receipts: pkg.receipts ?? [],
    items_to_copy: pkg.items_to_copy ?? [],
    installcheck_script: pkg.installcheck_script ?? '',
    uninstallcheck_script: pkg.uninstallcheck_script ?? '',
    version_script: pkg.version_script ?? '',
    preinstall_script: pkg.preinstall_script ?? '',
    postinstall_script: pkg.postinstall_script ?? '',
    preuninstall_script: pkg.preuninstall_script ?? '',
    postuninstall_script: pkg.postuninstall_script ?? '',
    notes: pkg.notes ?? '',
    restart_action: pkg.restart_action ?? '',
    on_demand: pkg.on_demand,
    force_install_after_date: pkg.force_install_after_date ?? '',
    apple_item: pkg.apple_item,
    installable_condition: pkg.installable_condition ?? '',
    package_path: pkg.package_path ?? '',
    package_complete_url: pkg.package_complete_url ?? '',
    minimum_munki_version: pkg.minimum_munki_version ?? '',
    installer_type: pkg.installer_type ?? '',
    installed_size: pkg.installed_size,
    uninstaller_item_location: pkg.uninstaller_item_location ?? '',
  }
}

export function buildUpdatePayload(
  original: EditableFields,
  edited: EditableFields,
): Record<string, unknown> {
  const payload: Record<string, unknown> = {}
  for (const key of Object.keys(edited) as (keyof EditableFields)[]) {
    const o = original[key]
    const e = edited[key]
    if (Array.isArray(o) && Array.isArray(e)) {
      if (JSON.stringify(o) !== JSON.stringify(e)) payload[key] = e
    } else if (o !== e) {
      if (typeof e === 'string') {
        payload[key] = e === '' ? null : e
      } else {
        payload[key] = e
      }
    }
  }
  return payload
}

const VERSION_SPECIFIC_FIELDS: (keyof EditableFields)[] = [
  'installer_item_location',
  'installer_item_hash',
  'installer_item_size',
  'package_path',
  'package_complete_url',
  'installed_size',
  'uninstaller_item_location',
  'receipts',
]

export function filterSharedPayload(
  payload: Record<string, unknown>,
): Record<string, unknown> {
  const out = { ...payload }
  for (const key of VERSION_SPECIFIC_FIELDS) {
    delete out[key]
  }
  return out
}

export function versionSpecificPayload(
  payload: Record<string, unknown>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const key of VERSION_SPECIFIC_FIELDS) {
    if (key in payload) out[key] = payload[key]
  }
  return out
}
