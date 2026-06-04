output "backend_runner_email" {
  description = "Email of the Cloud Run backend service account"
  value       = google_service_account.backend_runner.email
}

output "cloud_functions_runner_email" {
  description = "Email of the Cloud Functions runtime service account"
  value       = google_service_account.cloud_functions_runner.email
}

output "cloud_tasks_invoker_email" {
  description = "Email of the Cloud Tasks invoker service account"
  value       = google_service_account.cloud_tasks_invoker.email
}

output "github_actions_deployer_email" {
  description = "Email of the GitHub Actions deployer service account"
  value       = google_service_account.github_actions_deployer.email
}

output "github_actions_deployer_name" {
  description = "Full resource name of the GitHub Actions deployer SA"
  value       = google_service_account.github_actions_deployer.name
}

output "copilot_agent_runner_email" {
  description = "Email of the Cloud Run copilot agent service account"
  value       = google_service_account.copilot_agent_runner.email
}

output "transcription_worker_runner_email" {
  description = "Email of the Cloud Run transcription worker service account"
  value       = google_service_account.transcription_worker_runner.email
}

output "document_generation_runner_email" {
  description = "Email of the Cloud Run document generation worker service account"
  value       = google_service_account.document_generation_runner.email
}

output "frontend_runner_email" {
  description = "Email of the Cloud Run frontend service account"
  value       = google_service_account.frontend_runner.email
}

output "backend_local_gcs_signer_email" {
  description = "Email of the local GCS URL signer SA for development impersonation"
  value       = google_service_account.backend_local_gcs_signer.email
}
