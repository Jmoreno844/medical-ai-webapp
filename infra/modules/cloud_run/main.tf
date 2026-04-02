resource "google_cloud_run_v2_service" "backend" {
  project              = var.project_id
  name                 = var.service_name
  location             = var.region
  deletion_protection  = false
  ingress              = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = var.service_account_email

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    max_instance_request_concurrency = var.max_concurrency
    session_affinity                 = var.session_affinity
    timeout                          = var.timeout

    dynamic "vpc_access" {
      for_each = var.vpc_access == null ? [] : [var.vpc_access]
      content {
        egress = lookup(vpc_access.value, "egress", "PRIVATE_RANGES_ONLY")

        network_interfaces {
          network    = vpc_access.value.network
          subnetwork = vpc_access.value.subnetwork
        }
      }
    }

    dynamic "volumes" {
      for_each = var.cloud_sql_volume_enabled && var.cloud_sql_connection_name != "" ? [var.cloud_sql_connection_name] : []
      content {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [volumes.value]
        }
      }
    }

    containers {
      image = var.image

      ports {
        container_port = var.container_port
      }

      resources {
        limits = {
          cpu    = var.cpu
          memory = var.memory
        }
      }

      dynamic "volume_mounts" {
        for_each = var.cloud_sql_volume_enabled && var.cloud_sql_connection_name != "" ? [var.cloud_sql_connection_name] : []
        content {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }

      dynamic "env" {
        for_each = var.env_vars
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = var.secret_env_vars
        content {
          name = env.value.name
          value_source {
            secret_key_ref {
              secret  = env.value.secret_id
              version = lookup(env.value, "version", "latest")
            }
          }
        }
      }
    }

    dynamic "containers" {
      for_each = var.sidecars
      content {
        name    = containers.value.name
        image   = containers.value.image
        command = containers.value.command
        args    = containers.value.args

        dynamic "env" {
          for_each = containers.value.env_vars
          content {
            name  = env.key
            value = env.value
          }
        }
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  labels = var.labels

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
    ]
  }
}

resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  count = var.allow_unauthenticated ? 1 : 0

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
