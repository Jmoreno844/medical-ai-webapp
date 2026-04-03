resource "google_sql_database_instance" "main" {
  project          = var.project_id
  name             = var.instance_name
  region           = var.region
  database_version = var.database_version

  deletion_protection = var.deletion_protection

  settings {
    tier              = var.tier
    availability_type = var.availability_type
    disk_autoresize   = true
    disk_size         = var.disk_size_gb

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = var.tier != "db-f1-micro"
      start_time                     = "03:00"
    }

    ip_configuration {
      ipv4_enabled                                  = var.ipv4_enabled
      private_network                               = var.private_network
      enable_private_path_for_google_cloud_services = var.private_network != null

      dynamic "authorized_networks" {
        for_each = var.ipv4_enabled ? var.authorized_networks : []
        content {
          name  = authorized_networks.value.name
          value = authorized_networks.value.cidr
        }
      }
    }

    database_flags {
      name  = "max_connections"
      value = var.max_connections
    }

    dynamic "database_flags" {
      for_each = var.enable_iam_auth ? ["on"] : []
      content {
        name  = "cloudsql.iam_authentication"
        value = database_flags.value
      }
    }
  }
}

resource "google_sql_database" "app" {
  project  = var.project_id
  name     = var.database_name
  instance = google_sql_database_instance.main.name
}

resource "google_sql_database" "additional" {
  for_each = toset(var.additional_database_names)

  project  = var.project_id
  name     = each.value
  instance = google_sql_database_instance.main.name
}

resource "google_sql_user" "app" {
  count = var.database_user == null || var.database_password == null ? 0 : 1

  project  = var.project_id
  name     = var.database_user
  instance = google_sql_database_instance.main.name
  password = var.database_password
}

resource "google_sql_user" "iam_service_accounts" {
  for_each = toset(var.iam_database_users)

  project  = var.project_id
  name     = trimsuffix(each.value, ".gserviceaccount.com")
  instance = google_sql_database_instance.main.name
  type     = "CLOUD_IAM_SERVICE_ACCOUNT"
}
