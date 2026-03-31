output "cloud_run_url" {
  description = "Backend Cloud Run service URL"
  value       = module.cloud_run.service_url
}

output "cloud_function_urls" {
  description = "Cloud Functions URLs"
  value       = module.cloud_functions.function_urls
}

output "cloud_sql_connection_name" {
  description = "Cloud SQL connection name"
  value       = module.cloud_sql.connection_name
}

output "cloud_sql_public_ip" {
  description = "Cloud SQL public IP"
  value       = module.cloud_sql.public_ip
}

output "audio_bucket" {
  description = "Audio files bucket name"
  value       = module.storage_buckets.audio_bucket_name
}

output "frontend_bucket" {
  description = "Frontend SPA bucket name"
  value       = module.storage_buckets.frontend_bucket_name
}

output "artifact_registry_url" {
  description = "Artifact Registry Docker URL prefix"
  value       = module.artifact_registry.repository_url
}

output "backend_service_account" {
  description = "Cloud Run backend service account email"
  value       = module.service_accounts.backend_runner_email
}

output "cloud_functions_service_account" {
  description = "Cloud Functions runtime service account email"
  value       = module.service_accounts.cloud_functions_runner_email
}

output "workload_identity_provider" {
  description = "WIF provider path for GitHub Actions"
  value       = module.workload_identity.workload_identity_provider
}

output "github_actions_deployer_email" {
  description = "GitHub Actions deployer service account email"
  value       = module.service_accounts.github_actions_deployer_email
}
