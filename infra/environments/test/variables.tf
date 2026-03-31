variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
}

variable "environment" {
  description = "Environment name (test, prod)"
  type        = string
}

# --- GitHub ---

variable "github_repo" {
  description = "GitHub repository in 'owner/repo' format"
  type        = string
}

# --- Cloud SQL ---

variable "db_instance_name" {
  description = "Cloud SQL instance name"
  type        = string
}

variable "db_tier" {
  description = "Cloud SQL machine tier"
  type        = string
  default     = "db-f1-micro"
}

variable "db_name" {
  description = "Application database name"
  type        = string
}

variable "db_user" {
  description = "Application database user"
  type        = string
}

variable "db_password" {
  description = "Application database password"
  type        = string
  sensitive   = true
}

# --- Cloud Run ---

variable "cloud_run_service_name" {
  description = "Cloud Run backend service name"
  type        = string
}

variable "cloud_run_image" {
  description = "Initial Docker image for Cloud Run (CI/CD updates this)"
  type        = string
}

variable "cloud_run_max_instances" {
  description = "Maximum Cloud Run instances"
  type        = number
  default     = 1
}

variable "cloud_run_max_concurrency" {
  description = "Maximum requests per Cloud Run instance"
  type        = number
  default     = 250
}

variable "cloud_run_use_secret_manager" {
  description = "Whether Cloud Run should load env vars from Secret Manager"
  type        = bool
  default     = true
}

variable "cloud_run_allow_unauthenticated" {
  description = "Whether Cloud Run should allow unauthenticated invocations"
  type        = bool
  default     = true
}

# --- Cloud Functions source ---

variable "cf_source_bucket" {
  description = "GCS bucket containing Cloud Functions source code"
  type        = string
}

variable "cf_source_object" {
  description = "GCS object path for Cloud Functions source zip"
  type        = string
}

# --- Buckets ---

variable "audio_bucket_name" {
  description = "GCS bucket for audio files"
  type        = string
}

variable "frontend_bucket_name" {
  description = "GCS bucket for frontend SPA"
  type        = string
}

variable "frontend_public_read_enabled" {
  description = "Whether to grant allUsers read access to the frontend bucket"
  type        = bool
  default     = true
}

# --- Artifact Registry ---

variable "artifact_registry_repo" {
  description = "Artifact Registry repository name"
  type        = string
  default     = "vexthealth-containers"
}
