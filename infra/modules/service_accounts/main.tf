data "google_project" "current" {
  project_id = var.project_id
}

resource "google_service_account" "backend_runner" {
  project      = var.project_id
  account_id   = "backend-runner"
  display_name = "Cloud Run backend service account"
}

resource "google_service_account" "cloud_functions_runner" {
  project      = var.project_id
  account_id   = "cloud-functions-runner"
  display_name = "Cloud Functions runtime service account"
}

resource "google_service_account" "cloud_tasks_invoker" {
  project      = var.project_id
  account_id   = "cloud-tasks-invoker"
  display_name = "Cloud Tasks invoker (calls Cloud Functions)"
}

resource "google_service_account" "github_actions_deployer" {
  project      = var.project_id
  account_id   = "github-actions-deployer"
  display_name = "GitHub Actions CI/CD deployer (WIF)"
}

# ---------------------------------------------------------------------------
# backend-runner IAM
# ---------------------------------------------------------------------------

resource "google_project_iam_member" "backend_cloudsql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.backend_runner.email}"
}

resource "google_project_iam_member" "backend_secrets" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.backend_runner.email}"
}

resource "google_project_iam_member" "backend_cloudsql_instance_user" {
  project = var.project_id
  role    = "roles/cloudsql.instanceUser"
  member  = "serviceAccount:${google_service_account.backend_runner.email}"
}

resource "google_project_iam_member" "backend_trace" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.backend_runner.email}"
}

resource "google_project_iam_member" "backend_tasks_enqueue" {
  project = var.project_id
  role    = "roles/cloudtasks.enqueuer"
  member  = "serviceAccount:${google_service_account.backend_runner.email}"
}

# ---------------------------------------------------------------------------
# cloud-functions-runner IAM
# ---------------------------------------------------------------------------

resource "google_project_iam_member" "cf_aiplatform" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.cloud_functions_runner.email}"
}

resource "google_project_iam_member" "cf_trace" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.cloud_functions_runner.email}"
}

resource "google_project_iam_member" "cf_run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.cloud_functions_runner.email}"
}

resource "google_project_iam_member" "cf_secrets" {
  count   = var.grant_cloud_functions_secret_accessor ? 1 : 0
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.cloud_functions_runner.email}"
}

resource "google_project_iam_member" "gcf_build_source_reader" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

resource "google_project_iam_member" "gcf_build_logs_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

resource "google_project_iam_member" "gcf_build_artifact_registry_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

resource "google_project_iam_member" "gcf_build_artifact_registry_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

# ---------------------------------------------------------------------------
# cloud-tasks-invoker IAM (per-function binding is applied by the deploy workflow)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# github-actions-deployer IAM
# ---------------------------------------------------------------------------

resource "google_project_iam_member" "gh_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.github_actions_deployer.email}"
}

resource "google_project_iam_member" "gh_cf_developer" {
  project = var.project_id
  role    = "roles/cloudfunctions.developer"
  member  = "serviceAccount:${google_service_account.github_actions_deployer.email}"
}

resource "google_service_account_iam_member" "gh_cf_compute_sa_user" {
  service_account_id = "projects/${var.project_id}/serviceAccounts/${data.google_project.current.number}-compute@developer.gserviceaccount.com"
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.github_actions_deployer.email}"
}

resource "google_project_iam_member" "gh_cf_sa_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${google_service_account.github_actions_deployer.email}"
}

resource "google_project_iam_member" "gh_ar_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.github_actions_deployer.email}"
}

resource "google_storage_bucket_iam_member" "backend_audio_bucket_admin" {
  bucket = var.audio_bucket_name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.backend_runner.email}"
}

resource "google_storage_bucket_iam_member" "cf_audio_bucket_viewer" {
  bucket = var.audio_bucket_name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.cloud_functions_runner.email}"
}

resource "google_storage_bucket_iam_member" "gh_frontend_bucket_admin" {
  bucket = var.frontend_bucket_name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.github_actions_deployer.email}"
}

resource "google_storage_bucket_iam_member" "gh_cf_source_bucket_admin" {
  count  = var.cf_source_bucket_name == null ? 0 : 1
  bucket = var.cf_source_bucket_name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.github_actions_deployer.email}"
}

resource "google_service_account_iam_member" "gh_backend_runner_user" {
  service_account_id = google_service_account.backend_runner.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.github_actions_deployer.email}"
}

resource "google_service_account_iam_member" "gh_cloud_functions_runner_user" {
  service_account_id = google_service_account.cloud_functions_runner.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.github_actions_deployer.email}"
}

resource "google_service_account_iam_member" "backend_cloud_tasks_invoker_user" {
  service_account_id = google_service_account.cloud_tasks_invoker.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.backend_runner.email}"
}

resource "google_service_account_iam_member" "backend_cloud_tasks_invoker_token_creator" {
  service_account_id = google_service_account.cloud_tasks_invoker.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.backend_runner.email}"
}
