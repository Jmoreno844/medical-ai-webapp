output "pool_name" {
  description = "Full resource name of the WIF pool"
  value       = google_iam_workload_identity_pool.github.name
}

output "provider_name" {
  description = "Full resource name of the WIF provider"
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "workload_identity_provider" {
  description = "Provider resource path for use in GitHub Actions auth step"
  value       = google_iam_workload_identity_pool_provider.github.name
}
