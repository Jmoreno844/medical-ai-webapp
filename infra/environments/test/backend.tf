terraform {
  backend "gcs" {
    bucket = "vext-stg-terraform-state"
    prefix = "terraform/test"
  }
}
