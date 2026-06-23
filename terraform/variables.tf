variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "eastus2"
}

variable "name_prefix" {
  description = "Prefix used in resource names. Must be 3-15 chars, lowercase letters/numbers/dashes (storage accounts and ACR names have very restrictive rules)."
  type        = string
  default     = "munkimanager"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,14}$", var.name_prefix))
    error_message = "name_prefix must be 3-15 chars, lowercase, start with a letter."
  }
}

variable "environment" {
  description = "Environment tag value (single env, kept as a tag for future-proofing)."
  type        = string
  default     = "prod"
}

variable "extra_tags" {
  description = "Additional resource tags to merge with the defaults."
  type        = map(string)
  default     = {}
}

# --- Operator network access ---------------------------------------------

variable "operator_ip_allowlist" {
  description = <<EOT
List of operator IPv4 CIDRs that may reach the storage account control plane
(used for `az storage` commands and management-plane access). The Container
Apps env's outbound IP is added automatically — only put **operator** IPs
here. Public anonymous reads to the `munki-repo` blob container are NOT
firewalled (Munki clients keep working). Example: ["203.0.113.42/32"].
EOT
  type        = list(string)
  default     = []
}

# --- Custom domain --------------------------------------------------------

variable "custom_domain" {
  description = "Public hostname for the frontend Container App (e.g. munki-manager.joncra.in). Leave empty to skip custom-domain binding and use the auto-generated *.azurecontainerapps.io URL."
  type        = string
  default     = "munki-manager.joncra.in"
}

# --- Postgres -------------------------------------------------------------

variable "postgres_version" {
  description = "Postgres major version for Flexible Server."
  type        = string
  default     = "16"
}

variable "postgres_sku" {
  description = "Flexible Server SKU. B1ms is the cheapest (1 vCPU / 2 GiB)."
  type        = string
  default     = "B_Standard_B1ms"
}

variable "postgres_storage_mb" {
  description = "Storage size in MB. 32768 (32 GiB) is the smallest supported."
  type        = number
  default     = 32768
}

variable "postgres_admin_user" {
  description = "Postgres admin login name."
  type        = string
  default     = "munkiadmin"
}

variable "postgres_admin_password" {
  description = "Postgres admin password. Provide via -var or terraform.tfvars (do not commit). Used for the initial server creation; the app reads it from Key Vault."
  type        = string
  sensitive   = true
}

variable "postgres_db_name" {
  description = "Application database name."
  type        = string
  default     = "automunki"
}

# --- App secrets (written into Key Vault) --------------------------------

variable "app_secret_key" {
  description = "FastAPI JWT signing secret. Generate with `openssl rand -hex 32`."
  type        = string
  sensitive   = true
}

variable "github_token" {
  description = "GitHub PAT used by the backend for AutoPkg recipe / dispatch operations. Set to empty string to skip until you have one."
  type        = string
  sensitive   = true
  default     = ""
}

variable "github_repo" {
  description = "owner/repo for the AutoPkg recipe repository (non-secret)."
  type        = string
  default     = ""
}

variable "local_runner_token" {
  description = "Shared bearer token for poll_local_autopkg.sh runners. Generate with `openssl rand -hex 32`. Set to empty string to disable local runners."
  type        = string
  sensitive   = true
  default     = ""
}

variable "slack_webhook_url" {
  description = "Optional Slack webhook URL for notifications."
  type        = string
  sensitive   = true
  default     = ""
}

variable "gemini_api_key" {
  description = "Google Gemini API key for Admin AI Insights. Leave empty to disable."
  type        = string
  sensitive   = true
  default     = ""
}

variable "insights_enabled" {
  description = "Enable Admin AI Insights in the backend (requires gemini_api_key)."
  type        = bool
  default     = false
}

variable "gemini_model" {
  description = "Gemini model id for Admin AI Insights."
  type        = string
  default     = "gemini-3.1-flash-lite-preview"
}

variable "auth_demo_enabled" {
  description = "When true, the login page shows Try demo and POST /api/v1/auth/demo issues a read-only JWT (Viewer role). Keep false on admin instances; pair with AUTH_REGISTRATION_OPEN=false on public demos. Maps to AUTH_DEMO_ENABLED."
  type        = bool
  default     = false
}

variable "demo_jwt_lifetime_seconds" {
  description = "Optional shorter JWT lifetime for demo sessions (seconds). Null = use the backend default (same as JWT_LIFETIME_SECONDS). Maps to DEMO_JWT_LIFETIME_SECONDS."
  type        = number
  default     = null
  nullable    = true
}

# --- Container Apps sizing -----------------------------------------------

variable "backend_cpu" {
  description = "CPU cores for the backend container."
  type        = number
  default     = 0.5
}

variable "backend_memory" {
  description = "Memory for the backend container."
  type        = string
  default     = "1Gi"
}

variable "frontend_cpu" {
  description = "CPU cores for the frontend container."
  type        = number
  default     = 0.25
}

variable "frontend_memory" {
  description = "Memory for the frontend container."
  type        = string
  default     = "0.5Gi"
}

variable "backend_min_replicas" {
  description = "Minimum replicas for the backend (FastAPI). 0 = scale to zero (cheapest, ~5-15s cold start on first request after idle). 1 = always warm; recommended in production because lazy-loaded SPA chunks and live polling otherwise hit the cold-start window. At idle rates a single 0.5 vCPU / 1 GiB replica is roughly $3-8/mo above the free grant."
  type        = number
  default     = 1
}

variable "backend_max_replicas" {
  description = "Maximum replicas for the backend."
  type        = number
  default     = 3
}

variable "frontend_min_replicas" {
  description = "Minimum replicas for the frontend (nginx). Safe to keep at 0; nginx cold-starts in under a second and the SPA bundle is cached in the browser after first load."
  type        = number
  default     = 0
}

variable "frontend_max_replicas" {
  description = "Maximum replicas for the frontend."
  type        = number
  default     = 3
}

# --- Image tags (set by the deploy script) -------------------------------
#
# On first apply (before `make deploy` has pushed anything to ACR), the apps
# need to point at an image that already exists somewhere — otherwise Azure
# rejects the revision create with MANIFEST_UNKNOWN. We default to a public
# Microsoft hello-world image and only switch to the real ACR image once the
# operator runs `make deploy` (which sets var.backend_image_tag /
# frontend_image_tag to a real tag and re-applies).
#
# After the first `make deploy`, Terraform's `ignore_changes` on the image
# field means subsequent `tf-apply`s won't fight `az containerapp update`.

variable "bootstrap_backend_image" {
  description = "Image to point the backend at on first apply, before `make deploy` has populated ACR. Override only if you want to use a different placeholder."
  type        = string
  default     = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
}

variable "bootstrap_frontend_image" {
  description = "Image to point the frontend at on first apply, before `make deploy` has populated ACR."
  type        = string
  default     = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
}

variable "backend_image_tag" {
  description = "Backend image tag in ACR after `make deploy` has pushed at least once. Empty string = use bootstrap_backend_image instead. The Makefile injects a real tag (short git SHA) on `make deploy`."
  type        = string
  default     = ""
}

variable "frontend_image_tag" {
  description = "Frontend image tag in ACR after `make deploy` has pushed at least once. Empty string = use bootstrap_frontend_image instead."
  type        = string
  default     = ""
}
