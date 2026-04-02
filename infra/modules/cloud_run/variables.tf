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
  default     = ""
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

variable "container_port" {
  description = "Port exposed by the main application container"
  type        = number
  default     = 8080
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

variable "cloud_sql_volume_enabled" {
  description = "Whether to mount the Cloud SQL socket volume into the main container"
  type        = bool
  default     = true
}

variable "vpc_access" {
  description = "Optional Direct VPC egress configuration"
  type = object({
    network    = string
    subnetwork = string
    egress     = optional(string, "PRIVATE_RANGES_ONLY")
  })
  default = null
}

variable "sidecars" {
  description = "Additional sidecar containers"
  type = list(object({
    name     = string
    image    = string
    command  = optional(list(string), [])
    args     = optional(list(string), [])
    env_vars = optional(map(string), {})
  }))
  default = []
}

variable "labels" {
  description = "Labels to apply"
  type        = map(string)
  default     = {}
}
