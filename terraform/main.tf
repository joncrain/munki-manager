terraform {
  required_version = ">= 1.6.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.10"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "azurerm" {
  # Use AAD (the operator's `az login` identity / the CI federated SP) for
  # Storage data-plane reads instead of the storage account shared key.
  # REQUIRED when `azurerm_storage_account.repo` has
  # `shared_access_key_enabled = false` — otherwise the post-update state
  # refresh tries to read queue/table/file service properties via the
  # now-disabled shared key and fails with `KeyBasedAuthenticationNotPermitted`.
  #
  # The operator (or CI SP) must hold the matching data-plane roles on the
  # account: Storage Blob Data Owner + Storage Queue/Table Data Contributor +
  # Storage File Data Privileged Contributor. Those are granted by
  # `azurerm_role_assignment.operator_storage_*` in `storage.tf`.
  storage_use_azuread = true

  features {
    key_vault {
      # Hard-delete secrets on destroy so re-applying after a destroy works
      # without manual `az keyvault purge`. Fine for a demo; flip both to false
      # in prod so accidental destroys are recoverable.
      purge_soft_delete_on_destroy    = true
      recover_soft_deleted_key_vaults = true
    }
  }
}

# Resolve the running identity (used to grant the operator KV access on apply).
data "azurerm_client_config" "current" {}

# Stable global suffix used for resources that need a globally unique name
# (storage accounts, ACR, key vault). Stored in TF state so it doesn't change
# between applies.
resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
  numeric = true
}

locals {
  name_prefix = var.name_prefix
  suffix      = random_string.suffix.result

  tags = merge(
    {
      project     = "munki-manager"
      environment = var.environment
      managed_by  = "terraform"
    },
    var.extra_tags,
  )
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.name_prefix}"
  location = var.location
  tags     = local.tags
}

# User-assigned managed identity used by both Container Apps to (a) pull from
# ACR and (b) read secrets from Key Vault. One identity for both apps keeps
# RBAC simple.
resource "azurerm_user_assigned_identity" "apps" {
  name                = "id-${local.name_prefix}-apps"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.tags
}
