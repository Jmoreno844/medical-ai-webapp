variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "cloud_run_service_name" {
  description = "Primary backend Cloud Run service name"
  type        = string
}

variable "transcription_worker_service_name" {
  description = "Transcription worker Cloud Run service name"
  type        = string
  default     = ""
}

variable "document_pipeline_worker_service_name" {
  description = "Document generation worker Cloud Run service name"
  type        = string
  default     = ""
}

variable "cloud_function_service_names" {
  description = "Gen2 Cloud Function backing service names to monitor"
  type        = list(string)
  default     = []
}

variable "cloud_sql_instance_name" {
  description = "Cloud SQL instance name"
  type        = string
}

variable "monthly_budget_amount_usd" {
  description = "Monthly budget amount in USD"
  type        = number
  default     = 100
}

variable "billing_account_name" {
  description = "Billing account resource name used for budgets"
  type        = string
  default     = ""
}
