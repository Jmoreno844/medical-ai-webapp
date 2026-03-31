output "enabled_services" {
  description = "Set of enabled API services"
  value       = [for s in google_project_service.apis : s.service]
}
