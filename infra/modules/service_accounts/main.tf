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

resource "google_project_iam_member" "backend_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
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

resource "google_project_iam_member" "cf_storage" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
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
# cloud-tasks-invoker IAM (per-function binding is done in cloud_functions module)
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

resource "google_project_iam_member" "gh_storage_admin" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.github_actions_deployer.email}"
}

resource "google_project_iam_member" "gh_ar_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.github_actions_deployer.email}"
}

resource "google_project_iam_member" "gh_sa_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${google_service_account.github_actions_deployer.email}"
}
