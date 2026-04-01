# ---------------------------------------------------------------------------
# Audio bucket — 7-day lifecycle, no public access
# ---------------------------------------------------------------------------

resource "google_storage_bucket" "audio" {
  project                     = var.project_id
  name                        = var.audio_bucket_name
  location                    = var.region
  force_destroy               = var.force_destroy
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = false
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = var.audio_retention_days
    }
  }

  cors {
    origin          = var.audio_cors_origins
    method          = ["PUT", "GET", "HEAD", "OPTIONS", "DELETE"]
    response_header = ["Content-Type"]
    max_age_seconds = 3600
  }

  labels = var.labels
}

# ---------------------------------------------------------------------------
# Frontend SPA bucket — public read, website config
# ---------------------------------------------------------------------------

resource "google_storage_bucket" "frontend" {
  project                     = var.project_id
  name                        = var.frontend_bucket_name
  location                    = var.region
  force_destroy               = var.force_destroy
  uniform_bucket_level_access = true

  website {
    main_page_suffix = "index.html"
    not_found_page   = "index.html"
  }

  cors {
    origin          = var.frontend_cors_origins
    method          = ["GET", "HEAD"]
    response_header = ["Content-Type"]
    max_age_seconds = 3600
  }

  labels = var.labels
}

resource "google_storage_bucket" "cloud_functions_source" {
  count = var.cf_source_bucket_name == null ? 0 : 1

  project                     = var.project_id
  name                        = var.cf_source_bucket_name
  location                    = var.region
  force_destroy               = var.force_destroy
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  labels = var.labels
}

resource "google_storage_bucket_iam_member" "frontend_public_read" {
  count  = var.frontend_public_read_enabled ? 1 : 0
  bucket = google_storage_bucket.frontend.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}
