variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
}

variable "service_name" {
  description = "Cloud Run service name"
  type        = string
}

variable "image" {
  description = "Docker image to deploy (initial; CI/CD updates this)"
  type        = string
}

variable "service_account_email" {
  description = "Service account email for the Cloud Run service"
  type        = string
}

variable "cloud_sql_connection_name" {
  description = "Cloud SQL connection name (project:region:instance)"
  type        = string
}

variable "min_instances" {
  description = "Minimum number of instances"
  type        = number
  default     = 0
}

variable "max_instances" {
  description = "Maximum number of instances"
  type        = number
  default     = 1
}

variable "max_concurrency" {
  description = "Maximum requests per container instance"
  type        = number
  default     = 250
}

variable "session_affinity" {
  description = "Enable session affinity"
  type        = bool
  default     = true
}

variable "timeout" {
  description = "Request timeout (e.g. '300s')"
  type        = string
  default     = "300s"
}

variable "cpu" {
  description = "CPU limit"
  type        = string
  default     = "1"
}

variable "memory" {
  description = "Memory limit"
  type        = string
  default     = "1Gi"
}

variable "env_vars" {
  description = "Plain-text environment variables"
  type        = map(string)
  default     = {}
}

variable "secret_env_vars" {
  description = "Environment variables sourced from Secret Manager"
  type = list(object({
    name      = string
    secret_id = string
    version   = optional(string, "latest")
  }))
  default = []
}

variable "allow_unauthenticated" {
  description = "Allow unauthenticated invocations (public endpoint)"
  type        = bool
  default     = true
}

variable "labels" {
  description = "Labels to apply"
  type        = map(string)
  default     = {}
}
