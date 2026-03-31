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
