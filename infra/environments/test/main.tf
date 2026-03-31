# ============================================================================
# Root module — wires every infrastructure module for the test environment
# ============================================================================

locals {
  labels = {
    environment = var.environment
    managed_by  = "terraform"
  }
}

# ---------------------------------------------------------------------------
# 1. Enable GCP APIs
# ---------------------------------------------------------------------------

module "project_services" {
  source     = "../../modules/project_services"
  project_id = var.project_id

  services = [
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudfunctions.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "cloudtasks.googleapis.com",
    "cloudtrace.googleapis.com",
    "compute.googleapis.com",
    "containerregistry.googleapis.com",
    "eventarc.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "serviceusage.googleapis.com",
    "sqladmin.googleapis.com",
    "storage.googleapis.com",
    "sts.googleapis.com",
    "vpcaccess.googleapis.com",
  ]
}

# ---------------------------------------------------------------------------
# 2. Service accounts + IAM bindings
# ---------------------------------------------------------------------------

module "service_accounts" {
  source     = "../../modules/service_accounts"
  project_id = var.project_id

  depends_on = [module.project_services]
}

# ---------------------------------------------------------------------------
# 3. Workload Identity Federation (GitHub Actions)
# ---------------------------------------------------------------------------

module "workload_identity" {
  source     = "../../modules/workload_identity"
  project_id = var.project_id

  github_repo          = var.github_repo
  service_account_name = module.service_accounts.github_actions_deployer_name

  depends_on = [module.service_accounts]
}

# ---------------------------------------------------------------------------
# 4. Secret Manager (empty shells — values loaded manually)
# ---------------------------------------------------------------------------

module "secret_manager" {
  source     = "../../modules/secret_manager"
  project_id = var.project_id

  secret_ids = [
    "django-secret-key",
    "jwt-secret-key",
    "db-password",
    "db-user",
    "db-name",
    "service-account-json",
  ]

  labels = local.labels

  depends_on = [module.project_services]
}

# ---------------------------------------------------------------------------
# 5. Artifact Registry
# ---------------------------------------------------------------------------

module "artifact_registry" {
  source        = "../../modules/artifact_registry"
  project_id    = var.project_id
  region        = var.region
  repository_id = var.artifact_registry_repo
  labels        = local.labels

  depends_on = [module.project_services]
}

# ---------------------------------------------------------------------------
# 6. Cloud SQL
# ---------------------------------------------------------------------------

module "cloud_sql" {
  source            = "../../modules/cloud_sql"
  project_id        = var.project_id
  region            = var.region
  instance_name     = var.db_instance_name
  tier              = var.db_tier
  database_name     = var.db_name
  database_user     = var.db_user
  database_password = var.db_password

  deletion_protection = true

  depends_on = [module.project_services]
}

# ---------------------------------------------------------------------------
# 7. Storage buckets (audio + frontend)
# ---------------------------------------------------------------------------

module "storage_buckets" {
  source                       = "../../modules/storage_buckets"
  project_id                   = var.project_id
  region                       = var.region
  audio_bucket_name            = var.audio_bucket_name
  frontend_bucket_name         = var.frontend_bucket_name
  frontend_public_read_enabled = var.frontend_public_read_enabled
  audio_retention_days         = 7
  force_destroy                = true
  labels                       = local.labels

  depends_on = [module.project_services]
}

# ---------------------------------------------------------------------------
# 8. Cloud Tasks
# ---------------------------------------------------------------------------

module "cloud_tasks" {
  source     = "../../modules/cloud_tasks"
  project_id = var.project_id
  region     = var.region

  queue_name          = "audio-transcription-queue"
  max_attempts        = 3
  min_backoff_seconds = 10
  max_backoff_seconds = 300

  depends_on = [module.project_services]
}

# ---------------------------------------------------------------------------
# 9. Cloud Run (backend)
# ---------------------------------------------------------------------------

module "cloud_run" {
  source     = "../../modules/cloud_run"
  project_id = var.project_id
  region     = var.region

  service_name              = var.cloud_run_service_name
  image                     = var.cloud_run_image
  service_account_email     = module.service_accounts.backend_runner_email
  cloud_sql_connection_name = module.cloud_sql.connection_name

  min_instances    = 0
  max_instances    = var.cloud_run_max_instances
  max_concurrency  = var.cloud_run_max_concurrency
  session_affinity = true

  env_vars = {
    DJANGO_SETTINGS_MODULE   = "config.settings.test"
    ENVIRONMENT              = var.environment
    GCP_PROJECT_ID           = var.project_id
    GCS_BUCKET_NAME          = module.storage_buckets.audio_bucket_name
    ENABLE_SILK              = "true"
    INSTANCE_CONNECTION_NAME = module.cloud_sql.connection_name
  }

  secret_env_vars = var.cloud_run_use_secret_manager ? [
    { name = "SECRET_KEY", secret_id = "django-secret-key" },
    { name = "JWT_SECRET", secret_id = "jwt-secret-key" },
    { name = "DB_PASSWORD", secret_id = "db-password" },
    { name = "DB_USER", secret_id = "db-user" },
    { name = "DB_NAME", secret_id = "db-name" },
  ] : []

  allow_unauthenticated = var.cloud_run_allow_unauthenticated
  labels                = local.labels

  depends_on = [
    module.service_accounts,
    module.cloud_sql,
    module.secret_manager,
  ]
}

# ---------------------------------------------------------------------------
# 10. Cloud Functions (gen2, IAM-authenticated)
# ---------------------------------------------------------------------------

module "cloud_functions" {
  source     = "../../modules/cloud_functions"
  project_id = var.project_id
  region     = var.region

  runtime                       = "python312"
  runtime_service_account_email = module.service_accounts.cloud_functions_runner_email

  functions = [
    {
      name            = "transcription-endpoint"
      description     = "Transcribe audio from GCS and update document"
      entry_point     = "transcription_endpoint"
      source_bucket   = var.cf_source_bucket
      source_object   = var.cf_source_object
      max_instances   = 10
      memory          = "1Gi"
      timeout_seconds = 300
      env_vars = {
        GCP_PROJECT  = var.project_id
        GCP_REGION   = var.region
        GEMINI_MODEL = "gemini-2.0-flash"
        ENVIRONMENT  = var.environment
      }
      invoker_members = [
        "serviceAccount:${module.service_accounts.cloud_tasks_invoker_email}",
      ]
    },
    {
      name            = "document-workflow"
      description     = "Generate clinical documents with AI"
      entry_point     = "generate_document_workflow"
      source_bucket   = var.cf_source_bucket
      source_object   = var.cf_source_object
      max_instances   = 10
      memory          = "1Gi"
      timeout_seconds = 300
      env_vars = {
        GCP_PROJECT  = var.project_id
        GCP_REGION   = var.region
        GEMINI_MODEL = "gemini-2.0-flash"
        ENVIRONMENT  = var.environment
      }
      invoker_members = [
        "serviceAccount:${module.service_accounts.backend_runner_email}",
      ]
    },
  ]

  labels = local.labels

  depends_on = [
    module.service_accounts,
    module.project_services,
  ]
}
