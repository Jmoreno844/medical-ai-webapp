variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "services" {
  description = "List of GCP API service identifiers to enable"
  type        = list(string)
}
