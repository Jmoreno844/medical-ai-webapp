# ---------------------------------------------------------------------------
# Cloud Functions (Gen 2) — HTTP trigger, IAM-authenticated
# ---------------------------------------------------------------------------

resource "google_cloudfunctions2_function" "functions" {
  for_each = { for f in var.functions : f.name => f }

  project     = var.project_id
  name        = each.value.name
  location    = var.region
  description = each.value.description

  build_config {
    runtime     = var.runtime
    entry_point = each.value.entry_point

    source {
      storage_source {
        bucket = each.value.source_bucket
        object = each.value.source_object
      }
    }
  }

  service_config {
    min_instance_count    = each.value.min_instances
    max_instance_count    = each.value.max_instances
    available_memory      = each.value.memory
    timeout_seconds       = each.value.timeout_seconds
    service_account_email = var.runtime_service_account_email

    environment_variables = each.value.env_vars

    ingress_settings               = "ALLOW_ALL"
    all_traffic_on_latest_revision = true
  }

  labels = var.labels
}

# ---------------------------------------------------------------------------
# IAM: restrict invocation to specific service accounts
# ---------------------------------------------------------------------------

resource "google_cloudfunctions2_function_iam_member" "invokers" {
  for_each = { for b in local.invoker_bindings : "${b.function_name}-${b.member}" => b }

  project        = var.project_id
  location       = var.region
  cloud_function = each.value.function_name
  role           = "roles/cloudfunctions.invoker"
  member         = each.value.member

  depends_on = [google_cloudfunctions2_function.functions]
}

resource "google_cloud_run_service_iam_member" "cf_run_invokers" {
  for_each = { for b in local.invoker_bindings : "${b.function_name}-run-${b.member}" => b }

  project  = var.project_id
  location = var.region
  service  = each.value.function_name
  role     = "roles/run.invoker"
  member   = each.value.member

  depends_on = [google_cloudfunctions2_function.functions]
}

locals {
  invoker_bindings = flatten([
    for f in var.functions : [
      for m in f.invoker_members : {
        function_name = f.name
        member        = m
      }
    ]
  ])
}
