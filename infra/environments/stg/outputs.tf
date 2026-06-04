output "cloud_run_url" {
  description = "Backend Cloud Run service URL"
  value       = module.cloud_run.service_url
}

output "copilot_agent_cloud_run_url" {
  description = "Copilot agent Cloud Run service URL"
  value       = module.copilot_agent_cloud_run.service_url
}

output "frontend_cloud_run_url" {
  description = "Frontend Cloud Run service URL"
  value       = module.frontend_cloud_run.service_url
}

output "transcription_worker_cloud_run_url" {
  description = "Transcription worker Cloud Run service URL"
  value       = module.transcription_worker_cloud_run.service_url
}

output "document_generation_worker_cloud_run_url" {
  description = "Document generation worker Cloud Run service URL"
  value       = module.document_generation_worker_cloud_run.service_url
}

output "cloud_sql_connection_name" {
  description = "Cloud SQL connection name"
  value       = module.cloud_sql.connection_name
}

output "cloud_sql_private_ip" {
  description = "Cloud SQL private IP"
  value       = module.cloud_sql.private_ip
}

output "audio_bucket" {
  description = "Audio files bucket name"
  value       = module.storage_buckets.audio_bucket_name
}

output "frontend_bucket" {
  description = "Frontend SPA bucket name"
  value       = module.storage_buckets.frontend_bucket_name
}

output "cf_source_bucket" {
  description = "Cloud Functions source bucket name"
  value       = module.storage_buckets.cf_source_bucket_name
}

output "artifact_registry_url" {
  description = "Artifact Registry Docker URL prefix"
  value       = module.artifact_registry.repository_url
}

output "backend_service_account" {
  description = "Cloud Run backend service account email"
  value       = module.service_accounts.backend_runner_email
}

output "copilot_agent_service_account" {
  description = "Cloud Run copilot agent service account email"
  value       = module.service_accounts.copilot_agent_runner_email
}

output "transcription_worker_service_account" {
  description = "Cloud Run transcription worker service account email"
  value       = module.service_accounts.transcription_worker_runner_email
}

output "document_generation_worker_service_account" {
  description = "Cloud Run document generation worker service account email"
  value       = module.service_accounts.document_generation_runner_email
}

output "frontend_service_account" {
  description = "Cloud Run frontend service account email"
  value       = module.service_accounts.frontend_runner_email
}

output "cloud_functions_service_account" {
  description = "Cloud Functions runtime service account email"
  value       = module.service_accounts.cloud_functions_runner_email
}

output "cloud_tasks_invoker_service_account" {
  description = "Cloud Tasks invoker service account email"
  value       = module.service_accounts.cloud_tasks_invoker_email
}

output "cloud_tasks_queue_name" {
  description = "Cloud Tasks queue name"
  value       = module.cloud_tasks.queue_name
}

output "document_generation_cloud_tasks_queue_name" {
  description = "Document generation Cloud Tasks queue name"
  value       = module.document_generation_cloud_tasks.queue_name
}

output "workload_identity_provider" {
  description = "WIF provider path for GitHub Actions"
  value       = module.workload_identity.workload_identity_provider
}

output "github_actions_deployer_email" {
  description = "GitHub Actions deployer service account email"
  value       = module.service_accounts.github_actions_deployer_email
}

output "frontend_domain_name" {
  description = "Custom domain mapped to the staging frontend Cloud Run service, if enabled"
  value       = try(google_cloud_run_domain_mapping.frontend[0].name, null)
}

output "frontend_domain_resource_records" {
  description = "DNS records required by the staging frontend Cloud Run domain mapping, if enabled"
  value       = try(google_cloud_run_domain_mapping.frontend[0].status[0].resource_records, [])
}

output "backend_domain_name" {
  description = "Custom domain mapped to the staging backend Cloud Run service, if enabled"
  value       = try(google_cloud_run_domain_mapping.backend[0].name, null)
}

output "backend_domain_resource_records" {
  description = "DNS records required by the staging backend Cloud Run domain mapping, if enabled"
  value       = try(google_cloud_run_domain_mapping.backend[0].status[0].resource_records, [])
}
