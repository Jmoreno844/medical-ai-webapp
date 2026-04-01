output "audio_bucket_name" {
  description = "Name of the audio bucket"
  value       = google_storage_bucket.audio.name
}

output "audio_bucket_url" {
  description = "gsutil URL for the audio bucket"
  value       = google_storage_bucket.audio.url
}

output "frontend_bucket_name" {
  description = "Name of the frontend SPA bucket"
  value       = google_storage_bucket.frontend.name
}

output "frontend_bucket_url" {
  description = "Public URL for the frontend SPA bucket"
  value       = "https://storage.googleapis.com/${google_storage_bucket.frontend.name}"
}

output "cf_source_bucket_name" {
  description = "Name of the Cloud Functions source bucket"
  value       = try(google_storage_bucket.cloud_functions_source[0].name, null)
}
