variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "audio_bucket_name" {
  description = "Audio bucket name for bucket-level IAM bindings"
  type        = string
}

variable "frontend_bucket_name" {
  description = "Frontend bucket name for bucket-level IAM bindings"
  type        = string
}

variable "cf_source_bucket_name" {
  description = "Cloud Functions source bucket name for bucket-level IAM bindings"
  type        = string
  default     = null
}

variable "grant_cloud_functions_secret_accessor" {
  description = "Whether the Cloud Functions runtime SA should be able to read Secret Manager"
  type        = bool
  default     = true
}
