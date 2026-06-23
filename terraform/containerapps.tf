# Container Apps environment + the two apps (backend, frontend).
#
# CUSTOM-DOMAIN BOOTSTRAP REQUIRES TWO APPLIES:
#   1. First apply (var.enable_custom_domain = false, the default): creates the
#      env, the apps, and outputs the *.azurecontainerapps.io URL plus the
#      asuid validation token. You add the CNAME and asuid TXT in Cloudflare.
#   2. Second apply (set var.enable_custom_domain = true): binds the custom
#      hostname and provisions the free managed TLS cert.
# See docs/azure-deployment.md for the full flow.

resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${local.name_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

resource "azurerm_container_app_environment" "main" {
  name                       = "cae-${local.name_prefix}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  tags                       = local.tags
}

# --- Backend (FastAPI) ------------------------------------------------------

locals {
  # NOTE: DATABASE_URL is rendered into Key Vault (see
  # azurerm_key_vault_secret.database_url) and consumed as a single secret
  # binding — not constructed in env-var space, because Container Apps
  # doesn't interpolate `$(VAR)` between env vars.

  # Anonymous URL Munki clients fetch from when the auto-uploader places
  # packages under /munki-repo/pkgs/.
  munki_repo_pkg_base_url = format(
    "https://%s.blob.core.windows.net/%s/pkgs",
    azurerm_storage_account.repo.name,
    azurerm_storage_container.munki_repo.name,
  )

  # If a custom domain is configured, the public app URL points at it; until
  # then the auto-generated FQDN is used.
  public_app_url = var.enable_custom_domain && var.custom_domain != "" ? format("https://%s", var.custom_domain) : ""

  # Image resolution. Use the public hello-world image as a placeholder until
  # `make deploy` injects a real tag (short git SHA). After the first deploy,
  # `ignore_changes = [template[0].container[0].image]` keeps Terraform from
  # fighting `az containerapp update` on subsequent applies.
  backend_image = var.backend_image_tag == "" ? var.bootstrap_backend_image : (
    "${azurerm_container_registry.main.login_server}/munki-manager-backend:${var.backend_image_tag}"
  )
  frontend_image = var.frontend_image_tag == "" ? var.bootstrap_frontend_image : (
    "${azurerm_container_registry.main.login_server}/munki-manager-frontend:${var.frontend_image_tag}"
  )
}

resource "azurerm_container_app" "backend" {
  name                         = "ca-${local.name_prefix}-backend"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.apps.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.apps.id
  }

  # --- KV-backed secrets exposed to the container as `secretref:<name>` ---
  secret {
    name                = "app-secret-key"
    identity            = azurerm_user_assigned_identity.apps.id
    key_vault_secret_id = azurerm_key_vault_secret.app_secret_key.versionless_id
  }

  secret {
    name                = "database-password"
    identity            = azurerm_user_assigned_identity.apps.id
    key_vault_secret_id = azurerm_key_vault_secret.postgres_password.versionless_id
  }

  secret {
    name                = "database-url"
    identity            = azurerm_user_assigned_identity.apps.id
    key_vault_secret_id = azurerm_key_vault_secret.database_url.versionless_id
  }

  secret {
    name                = "github-token"
    identity            = azurerm_user_assigned_identity.apps.id
    key_vault_secret_id = azurerm_key_vault_secret.github_token.versionless_id
  }

  secret {
    name                = "local-runner-token"
    identity            = azurerm_user_assigned_identity.apps.id
    key_vault_secret_id = azurerm_key_vault_secret.local_runner_token.versionless_id
  }

  secret {
    name                = "slack-webhook-url"
    identity            = azurerm_user_assigned_identity.apps.id
    key_vault_secret_id = azurerm_key_vault_secret.slack_webhook_url.versionless_id
  }

  secret {
    name                = "gemini-api-key"
    identity            = azurerm_user_assigned_identity.apps.id
    key_vault_secret_id = azurerm_key_vault_secret.gemini_api_key.versionless_id
  }

  # NOTE: `azure-storage-connection-string` secret was removed in the security
  # review (finding 2.3.2). The backend now uses managed identity to write to
  # the storage account; see `azurerm_role_assignment.apps_blob_writer` in
  # `storage.tf` and the `DefaultAzureCredential` branch in
  # `backend/automunki/services/storage/azure_blob.py`.

  ingress {
    # We have to set external_enabled = true here even though only the
    # frontend is meant to be reachable from the internet. Container Apps'
    # internal-only ingress (`external_enabled = false`) currently fails to
    # route cross-app traffic in the same environment in some configurations
    # (the ingress LB returns the "This Container App is stopped or does
    # not exist" 404 page even when the revision is healthy). Using external
    # ingress lets the frontend reach the backend via the standard FQDN.
    # The backend is still protected by the JWT auth middleware on every
    # /api/v1/* route, but if you want defense in depth, add an
    # ip_security_restriction limiting traffic to your environment's static
    # IP (see terraform/outputs.tf -> environment_static_ip if you want to
    # add that).
    external_enabled = true
    target_port      = 8000
    transport        = "http"
    # allow_insecure_connections = true so nginx (frontend) can talk to the
    # backend over plain HTTP without forcing a 301 to HTTPS, which simplifies
    # the proxy chain. End users only ever hit the frontend's HTTPS LB.
    allow_insecure_connections = true

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = var.backend_min_replicas
    max_replicas = var.backend_max_replicas

    container {
      name   = "backend"
      image  = local.backend_image
      cpu    = var.backend_cpu
      memory = var.backend_memory

      # --- Plain env -----------------------------------------------------
      # DATABASE_URL is fetched as a single Key Vault-backed secret because
      # Container Apps doesn't do `$(VAR)` interpolation between env vars
      # (the value would be passed as a literal string). See keyvault.tf,
      # `azurerm_key_vault_secret.database_url`.
      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
      env {
        name        = "SECRET_KEY"
        secret_name = "app-secret-key"
      }
      env {
        name        = "GITHUB_TOKEN"
        secret_name = "github-token"
      }
      env {
        name  = "GITHUB_REPO"
        value = var.github_repo
      }
      env {
        name        = "LOCAL_RUNNER_TOKEN"
        secret_name = "local-runner-token"
      }
      env {
        name        = "SLACK_WEBHOOK_URL"
        secret_name = "slack-webhook-url"
      }
      env {
        name        = "GEMINI_API_KEY"
        secret_name = "gemini-api-key"
      }
      env {
        name  = "INSIGHTS_ENABLED"
        value = var.insights_enabled && var.gemini_api_key != "" ? "true" : "false"
      }
      env {
        name  = "GEMINI_MODEL"
        value = var.gemini_model
      }
      env {
        name  = "AUTH_MODE"
        value = "jwt"
      }
      env {
        name  = "AUTH_REGISTRATION_OPEN"
        value = "true"
      }
      env {
        name  = "AUTH_DEMO_ENABLED"
        value = var.auth_demo_enabled ? "true" : "false"
      }
      dynamic "env" {
        for_each = var.demo_jwt_lifetime_seconds != null ? [var.demo_jwt_lifetime_seconds] : []
        content {
          name  = "DEMO_JWT_LIFETIME_SECONDS"
          value = tostring(env.value)
        }
      }
      env {
        name  = "DEBUG"
        value = "false"
      }
      env {
        name  = "MUNKI_REPO_PKG_BASE_URL"
        value = local.munki_repo_pkg_base_url
      }
      env {
        # Streaming uploader backend. ``azure_blob`` enables
        # POST /api/v1/autopkg/runs/{id}/pkgs and POST /api/v1/munki/upload
        # to stream package bytes into the storage account configured below.
        # See docs/storage-backends.md.
        name  = "STORAGE_BACKEND"
        value = "azure_blob"
      }
      env {
        # With AZURE_STORAGE_CONNECTION_STRING unset and AZURE_STORAGE_SAS_TOKEN
        # unset, `azure_blob.py` falls into the `DefaultAzureCredential` branch
        # and authenticates as the user-assigned managed identity bound to this
        # Container App. The role assignment is in `storage.tf`.
        name  = "AZURE_STORAGE_ACCOUNT_NAME"
        value = azurerm_storage_account.repo.name
      }
      env {
        name  = "AZURE_STORAGE_CONTAINER"
        value = azurerm_storage_container.munki_repo.name
      }
      env {
        # REQUIRED with a USER-ASSIGNED MI: tells `ManagedIdentityCredential`
        # (the link in `DefaultAzureCredential`'s chain that handles MI) which
        # identity to request a token for. With a system-assigned MI this is
        # implicit, but UAMIs are ambiguous (a Container App could in
        # principle have several attached) so the SDK refuses to guess.
        # Without this, uploads fail with `ClientAuthenticationError:
        # DefaultAzureCredential failed to retrieve a token from the included
        # credentials.` even though the role assignment is correct.
        #
        # Note: `EnvironmentCredential` requires the *triple* of
        # `AZURE_CLIENT_ID` + `AZURE_TENANT_ID` + (`AZURE_CLIENT_SECRET` |
        # `AZURE_CLIENT_CERTIFICATE_PATH`); with only `AZURE_CLIENT_ID` set
        # it skips itself, so this env var is safe.
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.apps.client_id
      }
      # AZURE_STORAGE_CONNECTION_STRING intentionally not set — see the
      # removed secret block above and finding 2.3.2 in
      # `docs/security-overview.md`.
      env {
        name  = "PUBLIC_APP_URL"
        value = local.public_app_url
      }
      env {
        name  = "API_PUBLIC_URL"
        value = local.public_app_url
      }
      env {
        name  = "CORS_ORIGINS"
        value = local.public_app_url == "" ? "[]" : format("[\"%s\"]", local.public_app_url)
      }

      # FastAPI exposes /health (root, not under /api/v1). See
      # backend/automunki/main.py.
      readiness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/health"
      }
      liveness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/health"
      }
    }
  }

  lifecycle {
    # The image tag is rolled forward by `make deploy` (az containerapp update),
    # so don't fight that on the next `terraform apply`.
    ignore_changes = [
      template[0].container[0].image,
    ]
  }
}

# --- Frontend (nginx + Vite SPA) -------------------------------------------

resource "azurerm_container_app" "frontend" {
  name                         = "ca-${local.name_prefix}-frontend"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.apps.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.apps.id
  }

  ingress {
    external_enabled = true
    target_port      = 3000
    # Pin transport to HTTP/1.1 — "auto" can resolve to HTTP/2, which trips
    # up nginx-as-upstream consumers (we ran into 504s during initial
    # rollout that went away after pinning to http).
    transport = "http"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = var.frontend_min_replicas
    max_replicas = var.frontend_max_replicas

    container {
      name   = "frontend"
      image  = local.frontend_image
      cpu    = var.frontend_cpu
      memory = var.frontend_memory

      env {
        name = "BACKEND_URL"
        # Use the backend's external Container Apps FQDN with plain HTTP.
        # nginx in the frontend image proxies /api/* to this URL. The
        # backend's ingress is `allow_insecure_connections = true` so HTTP
        # is allowed (avoids a 301 -> HTTPS redirect that would loop).
        # The backend's FQDN is only published once the app exists, so we
        # construct it from the env's default domain here rather than
        # using azurerm_container_app.backend.ingress[0].fqdn (which would
        # create an order-of-operations dependency).
        value = "http://ca-${local.name_prefix}-backend.${azurerm_container_app_environment.main.default_domain}"
      }
      env {
        name  = "AUTH_ENABLED"
        value = "true"
      }

      # nginx serves the SPA bundle at /, which is always a 200 from the
      # try_files fallback. /api/* is a proxy passthrough to the backend,
      # which doesn't have /api/health (the backend's /health is at root) —
      # so probing / is the simplest cheap "is nginx alive" check.
      readiness_probe {
        transport = "HTTP"
        port      = 3000
        path      = "/"
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].container[0].image,
    ]
  }
}

# --- Custom domain + managed cert (gated by var.enable_custom_domain) -------
#
# Two-apply flow:
#   1. var.enable_custom_domain = false (default): create env + apps. Read the
#      `frontend_default_fqdn` output and create a CNAME in Cloudflare:
#         munki-manager.joncra.in CNAME ca-...-frontend.<env>.<region>.azurecontainerapps.io
#      Set Cloudflare proxy to "DNS only" (gray cloud) during validation.
#   2. var.enable_custom_domain = true: provisions the free managed cert
#      (CNAME-validated against the existing CNAME from step 1) and binds the
#      hostname to the frontend app with TLS.

variable "enable_custom_domain" {
  description = "Set true on the SECOND apply, after the Cloudflare CNAME is in place. See docs/azure-deployment.md."
  type        = bool
  default     = false
}

# Custom domain binding has a chicken-and-egg dependency with the managed
# certificate that the Terraform provider can't fully resolve on its own:
#
#   - azurerm_container_app_environment_managed_certificate requires the
#     hostname to ALREADY be bound to a Container App in the env (RequireCustomHostnameInEnvironment).
#   - azurerm_container_app_custom_domain requires a certificate ID to bind.
#
# In practice the cleanest sequence is:
#
#   1. terraform apply (with enable_custom_domain = false)  -> creates apps
#   2. add Cloudflare DNS:
#        CNAME munki-manager.<zone> -> <env-default-domain>  (DNS only / gray cloud)
#        TXT   asuid.munki-manager.<zone> -> <validation-token>
#      where <validation-token> is what `az containerapp hostname add ...`
#      tells you when it errors out the first time. The doc walks through it.
#   3. `az containerapp hostname add -g <rg> -n <app> --hostname <fqdn>`  (no cert yet)
#   4. `az containerapp env certificate create --validation-method CNAME ...`
#   5. `az containerapp hostname bind --thumbprint <cert-thumbprint> ...` to wire the cert
#
# The targets in `Makefile` (`make tf-domain`) automate steps 3–5.
# Terraform manages everything except the binding.
