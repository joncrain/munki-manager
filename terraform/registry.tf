# Azure Container Registry (Basic SKU is the cheapest, $5/mo, 10 GiB included).
# Container Apps pulls images from here using the user-assigned managed identity
# defined in main.tf — no admin user, no docker-config secret to rotate.

resource "azurerm_container_registry" "main" {
  # ACR names: 5-50 chars, lowercase alphanumerics, globally unique.
  name                = "acr${replace(local.name_prefix, "-", "")}${local.suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = false
  tags                = local.tags
}

resource "azurerm_role_assignment" "apps_acrpull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.apps.principal_id
}
