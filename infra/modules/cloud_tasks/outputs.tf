output "queue_name" {
  description = "Cloud Tasks queue name"
  value       = google_cloud_tasks_queue.transcription.name
}

output "queue_id" {
  description = "Cloud Tasks queue full resource ID"
  value       = google_cloud_tasks_queue.transcription.id
}
