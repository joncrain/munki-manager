# Azure Database for PostgreSQL Flexible Server.
#
# B1ms (Burstable, 1 vCPU, 2 GiB) + 32 GiB storage = ~$13-18/mo list price.
# Public access mode (no VNet) with a firewall rule allowing all Azure-internal
# IPs. Container Apps' outbound IPs are stable per environment but in the
# Microsoft-owned range, so "allow azure services" is the simplest path.
# Auth still required by password (which is in Key Vault).

resource "azurerm_postgresql_flexible_server" "main" {
  name                = "psql-${local.name_prefix}-${local.suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  version    = var.postgres_version
  sku_name   = var.postgres_sku
  storage_mb = var.postgres_storage_mb

  administrator_login    = var.postgres_admin_user
  administrator_password = var.postgres_admin_password

  # No HA, no backup-region replica — keep it cheap. PITR retention defaults to
  # 7 days, which is enough for a demo.
  backup_retention_days = 7

  # No zone or HA pinning so the platform places it where it's cheapest.
  zone = "1"

  public_network_access_enabled = true

  tags = local.tags

  lifecycle {
    ignore_changes = [
      # Azure may move it to a different zone after a maintenance event; don't
      # let that trigger a replacement.
      zone,
    ]
  }
}

resource "azurerm_postgresql_flexible_server_database" "automunki" {
  name      = var.postgres_db_name
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

# Allow Azure-internal services (incl. Container Apps) to connect.
# 0.0.0.0 -> 0.0.0.0 is the magic "allow Azure services" rule.
resource "azurerm_postgresql_flexible_server_firewall_rule" "allow_azure" {
  name             = "AllowAllAzureServices"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# Optional: when you run `terraform apply` from your laptop, you may want to
# connect to the DB to verify migrations. Uncomment and set your IP if so.
# resource "azurerm_postgresql_flexible_server_firewall_rule" "operator" {
#   name             = "operator-laptop"
#   server_id        = azurerm_postgresql_flexible_server.main.id
#   start_ip_address = "<your-public-ip>"
#   end_ip_address   = "<your-public-ip>"
# }
