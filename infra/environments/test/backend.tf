terraform {
  backend "gcs" {
    bucket = "vex-stg-terraform-state"
    prefix = "terraform/test"
  }
}
