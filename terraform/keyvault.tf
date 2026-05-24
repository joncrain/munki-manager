# Key Vault holds runtime secrets that the Container Apps reference at start.
# Container Apps native secrets are configured as `keyvaultref:<uri>` so the
# value is fetched on container start and refreshed on revision restart.

resource "azurerm_key_vault" "main" {
  # KV names: 3-24 chars, alphanumeric + dashes, globally unique.
  name                = substr("kv-${local.name_prefix}-${local.suffix}", 0, 24)
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  rbac_authorization_enabled    = true
  public_network_access_enabled = true

  # Soft delete + 7-day retention covers fat-finger destroys.
  soft_delete_retention_days = 7
  purge_protection_enabled   = false

  tags = local.tags
}

# Grant the operator running `terraform apply` permission to write secret values
# (otherwise the secret resources below fail with 403 Forbidden).
resource "azurerm_role_assignment" "operator_kv_admin" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

# Grant the Container Apps managed identity read access for KV references.
resource "azurerm_role_assignment" "apps_kv_reader" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.apps.principal_id
}

# --- Secrets ----------------------------------------------------------------

resource "azurerm_key_vault_secret" "app_secret_key" {
  name         = "app-secret-key"
  value        = var.app_secret_key
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.operator_kv_admin]
}

resource "azurerm_key_vault_secret" "postgres_password" {
  name         = "postgres-password"
  value        = var.postgres_admin_password
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.operator_kv_admin]
}

# Pre-rendered DATABASE_URL (asyncpg form) with the password baked in. We have
# to do this in Key Vault rather than constructing it in env-var space because
# Container Apps does NOT perform shell-style `$(VAR)` interpolation between
# env vars — a value like "postgresql://...:$(DATABASE_PASSWORD)@..." would
# be passed to the container as that literal string. The cleanest workaround
# is to store the full URL as a single secret and bind it to one env var.
resource "azurerm_key_vault_secret" "database_url" {
  name = "database-url"
  value = format(
    "postgresql+asyncpg://%s:%s@%s:5432/%s?ssl=require",
    var.postgres_admin_user,
    var.postgres_admin_password,
    azurerm_postgresql_flexible_server.main.fqdn,
    var.postgres_db_name,
  )
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.operator_kv_admin]
}

resource "azurerm_key_vault_secret" "github_token" {
  name = "github-token"
  # Empty values aren't allowed in Key Vault, so use a placeholder when unset.
  value        = var.github_token == "" ? "unset" : var.github_token
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.operator_kv_admin]
}

resource "azurerm_key_vault_secret" "local_runner_token" {
  name         = "local-runner-token"
  value        = var.local_runner_token == "" ? "unset" : var.local_runner_token
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.operator_kv_admin]
}

resource "azurerm_key_vault_secret" "slack_webhook_url" {
  name         = "slack-webhook-url"
  value        = var.slack_webhook_url == "" ? "unset" : var.slack_webhook_url
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.operator_kv_admin]
}

# NOTE: The storage account access key (`primary_connection_string`) used to
# be mirrored into Key Vault here as `azure-storage-connection-string`.
# Removed as part of the security review (finding 2.3.2): the backend now
# authenticates with managed identity (`Storage Blob Data Contributor` role
# assignment in `storage.tf`) and `shared_access_key_enabled = false` is set
# on the storage account, so even if a connection string ever leaked it
# would not be usable. Run
#   az keyvault secret delete --vault-name <name> --name azure-storage-connection-string
#   az keyvault secret purge  --vault-name <name> --name azure-storage-connection-string
# after `terraform apply` removes this resource, then rotate the storage
# account keys (`az storage account keys renew`) to invalidate any cached
# copies elsewhere.
