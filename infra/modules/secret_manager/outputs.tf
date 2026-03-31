output "secret_ids" {
  description = "Map of secret_id => full resource ID"
  value       = { for k, v in google_secret_manager_secret.secrets : k => v.id }
}

output "secret_names" {
  description = "Map of secret_id => full resource name"
  value       = { for k, v in google_secret_manager_secret.secrets : k => v.name }
}
