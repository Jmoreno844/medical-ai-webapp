output "function_urls" {
  description = "Map of function name => HTTPS URL"
  value       = { for k, v in google_cloudfunctions2_function.functions : k => v.service_config[0].uri }
}
