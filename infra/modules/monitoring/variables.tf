variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "cloud_run_service_name" {
  description = "Primary backend Cloud Run service name"
  type        = string
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
