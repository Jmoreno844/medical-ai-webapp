variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
}

variable "audio_bucket_name" {
  description = "Name of the audio files bucket"
  type        = string
}

variable "frontend_bucket_name" {
  description = "Name of the frontend SPA bucket"
  type        = string
}

variable "audio_retention_days" {
  description = "Days before audio objects are auto-deleted"
  type        = number
  default     = 7
}

variable "frontend_cors_origins" {
  description = "Allowed origins for CORS on the frontend bucket"
  type        = list(string)
  default     = ["*"]
}

variable "force_destroy" {
  description = "Allow Terraform to destroy buckets even if they contain objects"
  type        = bool
  default     = false
}

variable "labels" {
  description = "Labels to apply to buckets"
  type        = map(string)
  default     = {}
}
