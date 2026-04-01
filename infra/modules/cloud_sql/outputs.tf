output "instance_name" {
  description = "Cloud SQL instance name"
  value       = google_sql_database_instance.main.name
}

output "connection_name" {
  description = "Cloud SQL connection name (project:region:instance)"
  value       = google_sql_database_instance.main.connection_name
}

output "public_ip" {
  description = "Public IP address of the instance"
  value       = google_sql_database_instance.main.public_ip_address
}

output "private_ip" {
  description = "Private IP address of the instance"
  value       = google_sql_database_instance.main.private_ip_address
}

output "database_name" {
  description = "Name of the created database"
  value       = google_sql_database.app.name
}
