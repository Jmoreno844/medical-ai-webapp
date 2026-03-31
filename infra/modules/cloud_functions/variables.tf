variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
}

variable "runtime" {
  description = "Cloud Functions runtime (e.g. python312)"
  type        = string
  default     = "python312"
}

variable "runtime_service_account_email" {
  description = "Service account used by all Cloud Functions at runtime"
  type        = string
}

variable "functions" {
  description = "List of Cloud Functions to deploy"
  type = list(object({
    name            = string
    description     = string
    entry_point     = string
    source_bucket   = string
    source_object   = string
    min_instances   = optional(number, 0)
    max_instances   = optional(number, 10)
    memory          = optional(string, "1Gi")
    timeout_seconds = optional(number, 300)
    env_vars        = optional(map(string), {})
    invoker_members = list(string)
  }))
}

variable "labels" {
  description = "Labels to apply"
  type        = map(string)
  default     = {}
}
