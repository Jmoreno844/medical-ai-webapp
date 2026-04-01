variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "pool_id" {
  description = "Workload Identity Pool ID"
  type        = string
  default     = "github-actions-pool"
}

variable "provider_id" {
  description = "Workload Identity Pool Provider ID"
  type        = string
  default     = "github-oidc-provider"
}

variable "github_repo" {
  description = "GitHub repository in 'owner/repo' format"
  type        = string
}

variable "service_account_name" {
  description = "Full resource name of the SA to impersonate (projects/.../serviceAccounts/...)"
  type        = string
}

variable "allowed_refs" {
  description = "Git refs allowed to use this WIF provider"
  type        = list(string)
  default     = ["refs/heads/main"]
}

variable "allowed_workflow_files" {
  description = "Workflow files allowed to use this WIF provider"
  type        = list(string)
  default     = []
}
