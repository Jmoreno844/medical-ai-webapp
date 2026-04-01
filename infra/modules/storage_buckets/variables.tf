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

variable "cf_source_bucket_name" {
  description = "Name of the Cloud Functions source bucket"
  type        = string
  default     = null
}

variable "audio_retention_days" {
  description = "Days before audio objects are auto-deleted"
  type        = number
  default     = 7
}

variable "audio_cors_origins" {
  description = "Allowed browser origins for signed URL uploads to the audio bucket"
  type        = list(string)
  default = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
  ]
}

variable "frontend_cors_origins" {
  description = "Allowed origins for CORS on the frontend bucket"
  type        = list(string)
  default     = ["*"]
}

variable "frontend_public_read_enabled" {
  description = "Whether to grant allUsers read access to the frontend bucket"
  type        = bool
  default     = true
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
