variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
}

variable "network_name" {
  description = "VPC network name"
  type        = string
}

variable "subnetwork_name" {
  description = "Subnetwork name"
  type        = string
}

variable "subnetwork_cidr" {
  description = "Subnetwork CIDR range"
  type        = string
}

variable "private_service_range_name" {
  description = "Private service access range name"
  type        = string
}

variable "private_service_range_prefix_length" {
  description = "Prefix length for the private service access range"
  type        = number
  default     = 16
}
