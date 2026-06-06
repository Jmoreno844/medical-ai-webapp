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

variable "copilot_agent_db_name" {
  description = "Logical database name for copilot agent checkpoints and memory"
  type        = string
}

# --- Cloud Run ---

variable "cloud_run_service_name" {
  description = "Cloud Run backend service name"
  type        = string
}

variable "copilot_agent_service_name" {
  description = "Cloud Run copilot agent service name"
  type        = string
}

variable "frontend_service_name" {
  description = "Cloud Run frontend service name"
  type        = string
  default     = "vexthealth-frontend"
}

variable "transcription_worker_service_name" {
  description = "Cloud Run transcription worker service name"
  type        = string
  default     = "vexthealth-transcription-worker"
}

variable "document_generation_worker_service_name" {
  description = "Cloud Run document generation worker service name"
  type        = string
  default     = "vexthealth-document-generation-worker"
}

variable "admin_bootstrap_job_name" {
  description = "Cloud Run Job name for admin bootstrap operations"
  type        = string
  default     = "vexthealth-backend-admin-bootstrap"
}

variable "cloudsql_iam_grants_job_name" {
  description = "Cloud Run Job name for granting Cloud SQL schema/database privileges to IAM DB users"
  type        = string
  default     = "vexthealth-cloudsql-iam-grants"
}

variable "frontend_image" {
  description = "Initial Docker image for the frontend service (CI/CD updates this)"
  type        = string
}

variable "cloud_run_image" {
  description = "Initial Docker image for Cloud Run (CI/CD updates this)"
  type        = string
}

variable "copilot_agent_image" {
  description = "Initial Docker image for the copilot agent service (CI/CD updates this)"
  type        = string
}

variable "transcription_worker_image" {
  description = "Initial Docker image for the transcription worker service (CI/CD updates this)"
  type        = string
}

variable "document_generation_worker_image" {
  description = "Initial Docker image for the document generation worker service (CI/CD updates this)"
  type        = string
}

variable "frontend_max_instances" {
  description = "Maximum frontend Cloud Run instances"
  type        = number
  default     = 3
}

variable "frontend_max_concurrency" {
  description = "Maximum requests per frontend Cloud Run instance"
  type        = number
  default     = 80
}

variable "cloud_run_max_instances" {
  description = "Maximum Cloud Run instances"
  type        = number
  default     = 1
}

variable "copilot_agent_max_instances" {
  description = "Maximum copilot agent Cloud Run instances"
  type        = number
  default     = 2
}

variable "cloud_run_max_concurrency" {
  description = "Maximum requests per Cloud Run instance"
  type        = number
  default     = 250
}

variable "copilot_agent_max_concurrency" {
  description = "Maximum requests per copilot agent Cloud Run instance"
  type        = number
  default     = 20
}

variable "transcription_worker_max_instances" {
  description = "Maximum transcription worker Cloud Run instances"
  type        = number
  default     = 5
}

variable "document_generation_worker_max_instances" {
  description = "Maximum document generation worker Cloud Run instances"
  type        = number
  default     = 5
}

variable "transcription_worker_max_concurrency" {
  description = "Maximum requests per transcription worker Cloud Run instance"
  type        = number
  default     = 8
}

variable "document_generation_worker_max_concurrency" {
  description = "Maximum requests per document generation worker Cloud Run instance"
  type        = number
  default     = 8
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

variable "fastapi_cors_allowed_origins" {
  description = "Comma-separated CORS origins for FastAPI deploy-like workloads"
  type        = string
}

variable "copilot_agent_allow_unauthenticated" {
  description = "Whether the copilot agent service should allow unauthenticated invocations"
  type        = bool
  default     = false
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
  description = "Gemini model used by the transcription/document generation stack where applicable"
  type        = string
  default     = "gemini-3.1-flash-lite-preview"
}

variable "document_generation_provider" {
  description = "Provider used by the document generation worker"
  type        = string
  default     = "anthropic_api"
}

variable "document_generation_model" {
  description = "Explicit model override used by the document generation worker"
  type        = string
  default     = "claude-haiku-4-5-20251001"
}

variable "document_generation_google_model" {
  description = "Fallback Google Vertex model used by the document generation worker"
  type        = string
  default     = "gemini-3.1-flash-lite-preview"
}

variable "document_generation_vertex_ai_location" {
  description = "Vertex AI location used by the document generation worker when the provider runs on Vertex"
  type        = string
  default     = "global"
}

variable "frontend_public_read_enabled" {
  description = "Whether to grant allUsers read access to the frontend bucket"
  type        = bool
  default     = true
}

variable "frontend_domain_name" {
  description = "Custom domain mapped directly to the staging frontend Cloud Run service"
  type        = string
  default     = null
}

variable "backend_domain_name" {
  description = "Custom domain mapped directly to the staging backend Cloud Run service"
  type        = string
  default     = null
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

variable "monthly_budget_amount_usd" {
  description = "Monthly staging budget amount in USD"
  type        = number
  default     = 100
}

variable "billing_account_name" {
  description = "Billing account resource name used for the project budget"
  type        = string
  default     = ""
}
