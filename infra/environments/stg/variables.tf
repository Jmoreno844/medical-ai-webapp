variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
}

variable "environment" {
  description = "Environment name (stg, prod)"
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

variable "gemini_model" {
  description = "Gemini model used by Cloud Functions"
  type        = string
  default     = "gemini-3.1-flash-lite-preview"
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

# --- Networking / monitoring ---

variable "vpc_network_name" {
  description = "VPC network name for staging private services"
  type        = string
  default     = "vexthealth-stg-vpc"
}

variable "vpc_subnetwork_name" {
  description = "Subnetwork name for staging serverless workloads"
  type        = string
  default     = "stg-serverless-subnet"
}

variable "vpc_subnetwork_cidr" {
  description = "Subnetwork CIDR for staging serverless workloads"
  type        = string
  default     = "10.10.0.0/24"
}

variable "private_service_range_name" {
  description = "Name of the private service access range"
  type        = string
  default     = "stg-private-services-range"
}

variable "private_service_range_prefix_length" {
  description = "Prefix length for the private service access range"
  type        = number
  default     = 16
}

variable "cloud_run_db_proxy_image" {
  description = "Cloud SQL Auth Proxy image for the Cloud Run sidecar"
  type        = string
  default     = "gcr.io/cloud-sql-connectors/cloud-sql-proxy:2.14.1"
}

variable "cloud_functions_max_instances" {
  description = "Maximum instances for staging Cloud Functions"
  type        = number
  default     = 3
}

variable "monthly_budget_amount_usd" {
  description = "Monthly staging budget amount in USD"
  type        = number
  default     = 100
}
