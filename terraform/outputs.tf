output "resource_group" {
  description = "Resource group containing all Munki Manager resources."
  value       = azurerm_resource_group.main.name
}

output "acr_login_server" {
  description = "ACR login server. Use with `az acr build --registry <this>`."
  value       = azurerm_container_registry.main.login_server
}

output "acr_name" {
  description = "ACR name (without .azurecr.io suffix)."
  value       = azurerm_container_registry.main.name
}

output "backend_app_name" {
  description = "Container App name for the backend (used by `az containerapp update`)."
  value       = azurerm_container_app.backend.name
}

output "container_app_environment_name" {
  description = "Container Apps environment name (used by `az containerapp env certificate ...`)."
  value       = azurerm_container_app_environment.main.name
}

output "custom_domain" {
  description = "Custom domain for the frontend, if set."
  value       = var.custom_domain
}

output "frontend_app_name" {
  description = "Container App name for the frontend."
  value       = azurerm_container_app.frontend.name
}

output "frontend_default_fqdn" {
  description = "Default *.azurecontainerapps.io URL for the frontend. Use this as the CNAME target in Cloudflare."
  value       = azurerm_container_app.frontend.latest_revision_fqdn
}

output "frontend_default_url" {
  description = "Browse-able URL for the frontend before custom domain is configured."
  value       = "https://${azurerm_container_app.frontend.ingress[0].fqdn}"
}

output "custom_domain_url" {
  description = "Public URL once enable_custom_domain=true and DNS is in place."
  value       = var.enable_custom_domain && var.custom_domain != "" ? "https://${var.custom_domain}" : null
}

output "postgres_fqdn" {
  description = "Postgres Flexible Server FQDN (admin: var.postgres_admin_user)."
  value       = azurerm_postgresql_flexible_server.main.fqdn
}

output "key_vault_name" {
  description = "Key Vault holding app secrets. Update via `az keyvault secret set --vault-name <this> --name <secret> --value <value>` then restart the Container Apps."
  value       = azurerm_key_vault.main.name
}

output "storage_account_name" {
  description = "Storage account hosting the Munki package repository."
  value       = azurerm_storage_account.repo.name
}

output "munki_repo_pkg_base_url" {
  description = "Anonymous-read URL Munki clients fetch packages from. Set as MUNKI_REPO_PKG_BASE_URL on the backend (already done in containerapps.tf)."
  value       = "https://${azurerm_storage_account.repo.name}.blob.core.windows.net/${azurerm_storage_container.munki_repo.name}/pkgs"
}

output "next_steps" {
  description = "What to do after `terraform apply`."
  value = var.enable_custom_domain ? format(
    "Custom domain bound. Visit https://%s once DNS propagates and the cert issues (~5 min).",
    var.custom_domain,
    ) : format(
    "FIRST APPLY DONE. Next: (1) build & push images via `make deploy`. (2) In Cloudflare, create CNAME '%s' -> '%s' (DNS only / gray cloud). (3) Re-run `terraform apply -var enable_custom_domain=true`.",
    var.custom_domain,
    azurerm_container_app.frontend.latest_revision_fqdn,
  )
}
