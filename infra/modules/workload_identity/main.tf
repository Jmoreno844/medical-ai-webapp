resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = var.pool_id
  display_name              = "GitHub Actions"
  description               = "WIF pool for GitHub Actions CI/CD"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = var.provider_id
  display_name                       = "GitHub OIDC"
  description                        = "GitHub Actions OIDC provider"

  attribute_condition = local.attribute_condition

  attribute_mapping = {
    "google.subject"             = "assertion.sub"
    "attribute.actor"            = "assertion.actor"
    "attribute.repository"       = "assertion.repository"
    "attribute.ref"              = "assertion.ref"
    "attribute.job_workflow_ref" = "assertion.job_workflow_ref"
  }

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

locals {
  ref_condition_parts = [
    for ref in var.allowed_refs :
    "assertion.ref == \"${ref}\""
  ]

  workflow_condition_parts = flatten([
    for workflow in var.allowed_workflow_files : [
      for ref in var.allowed_refs :
      "assertion.job_workflow_ref == \"${var.github_repo}/${workflow}@${ref}\""
    ]
  ])

  attribute_condition = join(" && ", compact([
    "assertion.repository == \"${var.github_repo}\"",
    length(local.ref_condition_parts) > 0 ? "(${join(" || ", local.ref_condition_parts)})" : "",
    length(local.workflow_condition_parts) > 0 ? "(${join(" || ", local.workflow_condition_parts)})" : "",
  ]))
}

resource "google_service_account_iam_member" "wif_binding" {
  service_account_id = var.service_account_name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}
