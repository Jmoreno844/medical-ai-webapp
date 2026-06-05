variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
}

variable "job_name" {
  description = "Cloud Run Job name"
  type        = string
}

variable "image" {
  description = "Docker image to run"
  type        = string
}

variable "service_account_email" {
  description = "Service account email for the Cloud Run Job"
  type        = string
}

variable "command" {
  description = "Command for the main container"
  type        = list(string)
  default     = []
}

variable "args" {
  description = "Args for the main container"
  type        = list(string)
  default     = []
}

variable "task_count" {
  description = "Number of tasks"
  type        = number
  default     = 1
}

variable "parallelism" {
  description = "Parallelism for the job"
  type        = number
  default     = 1
}

variable "max_retries" {
  description = "Maximum task retries"
  type        = number
  default     = 0
}

variable "timeout" {
  description = "Task timeout (e.g. '600s')"
  type        = string
  default     = "600s"
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

variable "cloud_sql_connection_name" {
  description = "Cloud SQL connection name (project:region:instance)"
  type        = string
  default     = ""
}

variable "cloud_sql_volume_enabled" {
  description = "Whether to mount the Cloud SQL socket volume into the main container"
  type        = bool
  default     = false
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
