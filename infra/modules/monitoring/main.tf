locals {
  cloud_sql_database_id = "${var.project_id}:${var.cloud_sql_instance_name}"
  billing_account_id    = trimprefix(var.billing_account_name, "billingAccounts/")
}

resource "google_monitoring_alert_policy" "backend_cloud_run_5xx" {
  project       = var.project_id
  display_name  = "stg Cloud Run backend 5xx"
  combiner      = "OR"
  enabled       = true
  notification_channels = []

  documentation {
    content   = "Triggers when the staging backend returns HTTP 5xx responses."
    mime_type = "text/markdown"
  }

  conditions {
    display_name = "Backend Cloud Run 5xx responses"

    condition_threshold {
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "300s"
      filter          = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${var.cloud_run_service_name}\" AND metric.type=\"run.googleapis.com/request_count\" AND metric.labels.response_code_class=\"5xx\""

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.labels.service_name"]
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close = "1800s"
  }
}

resource "google_monitoring_alert_policy" "cloud_function_5xx" {
  for_each      = toset(var.cloud_function_service_names)
  project       = var.project_id
  display_name  = "stg Cloud Function ${each.value} 5xx"
  combiner      = "OR"
  enabled       = true
  notification_channels = []

  documentation {
    content   = "Triggers when the staging Cloud Function backing service ${each.value} returns HTTP 5xx responses."
    mime_type = "text/markdown"
  }

  conditions {
    display_name = "Cloud Function ${each.value} 5xx responses"

    condition_threshold {
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "300s"
      filter          = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${each.value}\" AND metric.type=\"run.googleapis.com/request_count\" AND metric.labels.response_code_class=\"5xx\""

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.labels.service_name"]
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close = "1800s"
  }
}

resource "google_monitoring_alert_policy" "cloud_sql_cpu" {
  project       = var.project_id
  display_name  = "stg Cloud SQL CPU high"
  combiner      = "OR"
  enabled       = true
  notification_channels = []

  documentation {
    content   = "Triggers when staging Cloud SQL CPU utilization stays above 80% for five minutes."
    mime_type = "text/markdown"
  }

  conditions {
    display_name = "Cloud SQL CPU utilization"

    condition_threshold {
      comparison      = "COMPARISON_GT"
      threshold_value = 0.8
      duration        = "300s"
      filter          = "resource.type=\"cloudsql_database\" AND resource.labels.database_id=\"${local.cloud_sql_database_id}\" AND metric.type=\"cloudsql.googleapis.com/database/cpu/utilization\""

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_MEAN"
        cross_series_reducer = "REDUCE_MEAN"
        group_by_fields      = ["resource.labels.database_id"]
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close = "1800s"
  }
}

resource "google_billing_budget" "project_budget" {
  count           = var.billing_account_name == "" ? 0 : 1
  billing_account = local.billing_account_id
  display_name    = "stg monthly budget"

  budget_filter {
    projects = ["projects/${var.project_id}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.monthly_budget_amount_usd)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }

  threshold_rules {
    threshold_percent = 0.9
  }

  threshold_rules {
    threshold_percent = 1.0
  }
}
