# Azure Storage Account hosting the Munki package repository.
#
# Auth model:
#   - Munki clients fetch pkgs anonymously over HTTPS from the public
#     `munki-repo` container (`container_access_type = "blob"`). This matches
#     the S3+CloudFront model and is required because Munki's downloader
#     drops `Authorization` on cross-origin 302s, so we can't put an
#     authenticating proxy in front today.
#   - The backend authenticates with **managed identity** (no shared keys),
#     via `Storage Blob Data Contributor` on this account. See
#     `azurerm_role_assignment.apps_blob_writer` below and the
#     `DefaultAzureCredential` branch in
#     `backend/automunki/services/storage/azure_blob.py`.
#   - Shared-key (account key) auth is **disabled** at the account level —
#     a leak of the connection string from Key Vault, an env var dump, or a
#     stack trace can't be turned into storage access.
#   - The control plane is firewalled (`azurerm_storage_account_network_rules`
#     resource) **once `var.operator_ip_allowlist` is set**: only the
#     Container Apps environment outbound IP and operator IPs may issue
#     authenticated/management requests. The firewall is gated on the
#     operator allowlist being non-empty so the operator doesn't lock
#     themselves out of subsequent terraform refreshes. Public anonymous
#     reads to the `munki-repo` container bypass the firewall by design
#     (Azure docs: "Network security rules don't apply to public anonymous
#     access.").
#
# Layout under the container:
#   /pkgs/<recipe>/<file>.pkg                  — Munki packages
#   /icons/<file>.png                          — optional icon mirror
#   /client_resources/<file>.zip               — Munki client resources
#
# MUNKI_REPO_PKG_BASE_URL is then:
#   https://<account>.blob.core.windows.net/munki-repo/pkgs

resource "azurerm_storage_account" "repo" {
  # Storage account names: 3-24 chars, lowercase alphanumeric only, globally unique.
  name                     = substr("st${replace(local.name_prefix, "-", "")}${local.suffix}", 0, 24)
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"

  # The operator's data-plane role grants (below) must exist before this
  # account is created — otherwise the post-create state read fails with 403
  # `KeyBasedAuthenticationNotPermitted` (provider uses AAD via
  # `provider.storage_use_azuread = true`, and AAD auth needs the matching
  # data-plane roles). The role grants are at the RG scope so they're
  # inherited by every storage account created in the RG.
  depends_on = [
    azurerm_role_assignment.operator_storage_blob_owner,
    azurerm_role_assignment.operator_storage_queue,
    azurerm_role_assignment.operator_storage_table,
    azurerm_role_assignment.operator_storage_file,
  ]

  # Required to allow public blob access on individual containers.
  allow_nested_items_to_be_public = true

  # No need for HNS (data lake) or SFTP for this workload.
  is_hns_enabled = false

  # Disable shared-key auth account-wide. Forces every authenticated caller
  # (the backend, operators using `az`) to use AAD/managed identity. Public
  # anonymous reads on the `munki-repo` container are unaffected by this
  # flag — they don't carry credentials.
  shared_access_key_enabled = false

  # Pin the minimum TLS version explicitly. The provider default already
  # tracks `TLS1_2` but pinning protects against future regressions.
  min_tls_version = "TLS1_2"

  # Public network access stays on at the account level, but the
  # `azurerm_storage_account_network_rules` resource below denies by default
  # and only allows the env's outbound IP + operator IPs. Anonymous reads on
  # the public container are exempt.
  public_network_access_enabled = true

  blob_properties {
    # Cheap PITR-ish: 7 days of soft delete on accidentally overwritten/deleted
    # blobs. Adds essentially nothing to cost at this scale.
    delete_retention_policy {
      days = 7
    }
    container_delete_retention_policy {
      days = 7
    }
  }

  tags = local.tags
}

# Storage account firewall.
#
# `default_action = "Deny"` blocks management-plane and authenticated data-plane
# calls from any IP not in the allowlist. The Container Apps environment talks
# to the storage account from a single static outbound IP (`static_ip_address`
# on the env), so we allow that. Operator laptops are added via
# `var.operator_ip_allowlist` (a list of CIDRs supplied in tfvars).
#
# Public anonymous read to the `munki-repo` container is **not** subject to
# these rules per Azure's documented behavior — Munki clients keep working.
#
# Gated on `var.operator_ip_allowlist` being non-empty so the operator
# explicitly opts into the firewall by listing their own IP first. Without
# this gate, the first apply would succeed (network rules are created last)
# but every subsequent `terraform plan/apply` would fail to refresh state
# because the operator's machine couldn't reach the storage data plane to
# read service properties (queue/table/file/blob). Set the variable in
# `terraform.tfvars` once you have the account locked-down posture you want.
resource "azurerm_storage_account_network_rules" "repo" {
  count = length(var.operator_ip_allowlist) > 0 ? 1 : 0

  storage_account_id = azurerm_storage_account.repo.id

  default_action = "Deny"

  # Bypass `AzureServices` so Microsoft-trusted services (diagnostic settings,
  # KV references when we ever store blobs there, Defender for Storage scans)
  # keep working. Container Apps egress does *not* count as a "trusted Azure
  # service", which is why we still need the explicit IP rule below.
  bypass = ["AzureServices"]

  # Allow the Container Apps env's egress IP for backend uploads.
  # Plus operator IPs supplied in tfvars.
  ip_rules = concat(
    [azurerm_container_app_environment.main.static_ip_address],
    var.operator_ip_allowlist,
  )
}

resource "azurerm_storage_container" "munki_repo" {
  name                  = "munki-repo"
  storage_account_id    = azurerm_storage_account.repo.id
  container_access_type = "blob" # anonymous read on individual blobs (not list)
}

# Grant the Container Apps managed identity the right to read/write blobs in
# this account. Replaces the connection-string-in-Key-Vault auth model.
#
# `Storage Blob Data Contributor` covers list / read / write / delete on
# blobs; it does NOT grant management-plane rights (create-container,
# rotate-keys), which is what we want — the container is Terraform-managed.
resource "azurerm_role_assignment" "apps_blob_writer" {
  scope                = azurerm_storage_account.repo.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.apps.principal_id
}

# --- Operator data-plane access -------------------------------------------
#
# When `shared_access_key_enabled = false` and `provider.storage_use_azuread
# = true`, the azurerm provider authenticates its state-refresh reads
# (queue/table/file/blob service properties) with the operator's AAD
# identity at the start of every plan/apply. The operator therefore needs
# the matching data-plane roles on this account, or every plan/apply will
# fail with 403 `KeyBasedAuthenticationNotPermitted` before terraform even
# computes the diff.
#
# These are scoped to the **resource group** (not to the storage account
# itself) so they exist before the storage account does on a fresh deploy
# and the post-create AAD read succeeds. The storage account `depends_on`
# these resources to enforce the create-order.
#
# Recovery (existing deployment that hit the chicken-and-egg) — run a
# targeted apply once from inside `terraform/` to create just the role
# assignments, then a normal apply:
#
#   cd terraform
#   terraform apply \
#     -target=azurerm_role_assignment.operator_storage_blob_owner \
#     -target=azurerm_role_assignment.operator_storage_queue \
#     -target=azurerm_role_assignment.operator_storage_table \
#     -target=azurerm_role_assignment.operator_storage_file
#   make tf-apply
#
# CI / federated-credential SP needs the same four roles assigned to its
# `principalId`. See docs/azure-deployment.md (`### One-time bootstrap`
# section).

resource "azurerm_role_assignment" "operator_storage_blob_owner" {
  scope                = azurerm_resource_group.main.id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "operator_storage_queue" {
  scope                = azurerm_resource_group.main.id
  role_definition_name = "Storage Queue Data Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "operator_storage_table" {
  scope                = azurerm_resource_group.main.id
  role_definition_name = "Storage Table Data Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "operator_storage_file" {
  scope                = azurerm_resource_group.main.id
  role_definition_name = "Storage File Data Privileged Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}
