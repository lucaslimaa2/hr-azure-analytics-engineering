# ── Terraform & provider setup ───────────────────────────────────────────────
# Declares which providers this config needs and pins their versions.
terraform {
  required_version = ">= 1.5"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    # Generates a random suffix so the storage account name is globally unique.
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

# The Azure provider. The empty `features {}` block is required by azurerm.
# It authenticates using your `az login` session — no keys or passwords in code.
provider "azurerm" {
  features {}
  subscription_id = "42e527bf-35ec-413d-b841-394ab1e60728"

  # University-managed subscriptions usually forbid registering resource
  # providers, which makes Terraform hang. Skip auto-registration; we register
  # the few providers we need manually (e.g. Microsoft.Storage) via `az`.
  resource_provider_registrations = "none"
}

# ── Resource group ───────────────────────────────────────────────────────────
# A logical container that holds every resource for this project, so the whole
# stack can be managed (and torn down) as one unit. Region: Brazil South (LGPD).
resource "azurerm_resource_group" "hr" {
  name     = "hr-data-rg"
  location = "brazilsouth"
}

# ── Data lake (ADLS Gen2) ────────────────────────────────────────────────────
# A 6-char random suffix to make the storage account name globally unique.
resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

# The storage account, with hierarchical namespace ON = ADLS Gen2 (a data lake).
resource "azurerm_storage_account" "lake" {
  name                     = "hrdatalake${random_string.suffix.result}"
  resource_group_name      = azurerm_resource_group.hr.name
  location                 = azurerm_resource_group.hr.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  is_hns_enabled           = true # ← turns plain blob storage into a Data Lake
}

# ── Lake zones ───────────────────────────────────────────────────────────────
# Two top-level filesystems (containers) — our two layers. Partition folders
# ({yyyy}/{MM}/) are created inside these when data is written.
resource "azurerm_storage_data_lake_gen2_filesystem" "raw" {
  name               = "raw"
  storage_account_id = azurerm_storage_account.lake.id
}

resource "azurerm_storage_data_lake_gen2_filesystem" "curated" {
  name               = "curated"
  storage_account_id = azurerm_storage_account.lake.id
}

# ── Data-plane access (RBAC) ─────────────────────────────────────────────────
# Who is running Terraform (your `az login` identity).
data "azurerm_client_config" "current" {}

# Subscription Owner lets you MANAGE the storage account but NOT read/write the
# data inside it. This grants your identity the data-plane role so the pipeline
# (and our local backfill script) can write to the lake.
resource "azurerm_role_assignment" "lake_data_contributor" {
  scope                = azurerm_storage_account.lake.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}

# ── Synapse workspace (hosts the serverless SQL pool + Studio) ────────────────
# The workspace needs its own filesystem in the lake for metadata/logs.
resource "azurerm_storage_data_lake_gen2_filesystem" "synapse" {
  name               = "synapse"
  storage_account_id = azurerm_storage_account.lake.id
}

# SQL admin password — Terraform generates it (kept in state). We connect via
# Azure AD (az login), so this is just to satisfy the required field.
resource "random_password" "sql_admin" {
  length           = 24
  special          = true
  override_special = "_%-"
}

resource "azurerm_synapse_workspace" "hr" {
  name                                 = "hr-synapse-${random_string.suffix.result}" # globally unique
  resource_group_name                  = azurerm_resource_group.hr.name
  location                             = azurerm_resource_group.hr.location
  storage_data_lake_gen2_filesystem_id = azurerm_storage_data_lake_gen2_filesystem.synapse.id
  sql_administrator_login              = "sqladmin"
  sql_administrator_login_password     = random_password.sql_admin.result

  identity {
    type = "SystemAssigned" # the workspace gets its own identity
  }
}

# Make YOUR az-login identity the workspace's Azure AD admin, so you can connect
# to the serverless SQL pool with your own credentials (no SQL password needed).
resource "azurerm_synapse_workspace_aad_admin" "me" {
  synapse_workspace_id = azurerm_synapse_workspace.hr.id
  login                = "aad-admin"
  object_id            = data.azurerm_client_config.current.object_id
  tenant_id            = data.azurerm_client_config.current.tenant_id
}

# Let your machine reach the workspace SQL endpoints (dev: allow all IPs — not
# production-secure, fine for learning).
resource "azurerm_synapse_firewall_rule" "allow_all_dev" {
  name                 = "allow-all-dev"
  synapse_workspace_id = azurerm_synapse_workspace.hr.id
  start_ip_address     = "0.0.0.0"
  end_ip_address       = "255.255.255.255"
}

# The serverless pool runs as the workspace identity — grant it data access to
# the lake so it can read raw and write curated (CETAS).
resource "azurerm_role_assignment" "synapse_lake_data" {
  scope                = azurerm_storage_account.lake.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_synapse_workspace.hr.identity[0].principal_id
}

# ── Generate Function (NOT deployed — kept as a note) ────────────────────────
# The production design hosts the Generate step as an Azure Function App (Python,
# Consumption plan) that Synapse's pipeline calls. We authored that stack here, but
# this subscription (a UNIFOR-managed tenant) has App Service quota = 0, so the plan
# can't be created ("Current Limit (Total VMs): 0"). Rather than host compute we
# can't provision, the Generate step runs in **GitHub Actions** instead (see
# .github/workflows/), and the transform runs on the serverless SQL pool above.
# The Function App Terraform is preserved in git history if a quota-enabled
# subscription is ever used.
