# Handy values surfaced after `terraform apply` — run `terraform output` to see them.

output "resource_group" {
  description = "Resource group holding the whole stack."
  value       = azurerm_resource_group.hr.name
}

output "lake_url" {
  description = "ADLS Gen2 dfs endpoint (STORAGE_ACCOUNT_URL for local runs / the Function)."
  value       = "https://${azurerm_storage_account.lake.name}.dfs.core.windows.net"
}

output "synapse_serverless_endpoint" {
  description = "Serverless SQL endpoint — connect Synapse Studio / tools here."
  value       = azurerm_synapse_workspace.hr.connectivity_endpoints["sqlOnDemand"]
}
