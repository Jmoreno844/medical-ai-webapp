variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
}

variable "instance_name" {
  description = "Cloud SQL instance name"
  type        = string
}

variable "database_version" {
  description = "PostgreSQL version"
  type        = string
  default     = "POSTGRES_15"
}

variable "tier" {
  description = "Machine tier (e.g. db-f1-micro, db-custom-1-3840)"
  type        = string
  default     = "db-f1-micro"
}

variable "availability_type" {
  description = "ZONAL or REGIONAL"
  type        = string
  default     = "ZONAL"
}

variable "disk_size_gb" {
  description = "Initial disk size in GB"
  type        = number
  default     = 10
}

variable "deletion_protection" {
  description = "Prevent accidental deletion of the instance"
  type        = bool
  default     = true
}

variable "max_connections" {
  description = "PostgreSQL max_connections flag"
  type        = string
  default     = "100"
}

variable "database_name" {
  description = "Name of the application database"
  type        = string
}

variable "database_user" {
  description = "Name of the application database user"
  type        = string
}

variable "database_password" {
  description = "Password for the application database user (use a sensitive variable)"
  type        = string
  sensitive   = true
}

variable "authorized_networks" {
  description = "CIDR blocks allowed to connect to the instance (public IP)"
  type = list(object({
    name = string
    cidr = string
  }))
  default = []
}
