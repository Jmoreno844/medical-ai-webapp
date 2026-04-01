output "network_id" {
  description = "VPC network resource ID"
  value       = google_compute_network.main.id
}

output "network_name" {
  description = "VPC network name"
  value       = google_compute_network.main.name
}

output "subnetwork_id" {
  description = "Subnetwork resource ID"
  value       = google_compute_subnetwork.serverless.id
}

output "subnetwork_name" {
  description = "Subnetwork name"
  value       = google_compute_subnetwork.serverless.name
}
