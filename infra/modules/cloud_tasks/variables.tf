variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
}

variable "queue_name" {
  description = "Cloud Tasks queue name"
  type        = string
  default     = "audio-transcription-queue"
}

variable "max_dispatches_per_second" {
  description = "Maximum rate of task dispatches"
  type        = number
  default     = 10
}

variable "max_concurrent_dispatches" {
  description = "Maximum concurrent task dispatches"
  type        = number
  default     = 5
}

variable "max_attempts" {
  description = "Maximum number of retry attempts"
  type        = number
  default     = 3
}

variable "min_backoff_seconds" {
  description = "Minimum backoff between retries"
  type        = number
  default     = 10
}

variable "max_backoff_seconds" {
  description = "Maximum backoff between retries"
  type        = number
  default     = 300
}

variable "max_retry_duration_seconds" {
  description = "Maximum total time for retries (0 = unlimited)"
  type        = number
  default     = 0
}
