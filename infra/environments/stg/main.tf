# ============================================================================
# Root module — wires every infrastructure module for the staging environment
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
    "billingbudgets.googleapis.com",
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
    "servicenetworking.googleapis.com",
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

# 2. Network (private services + serverless egress)
# ---------------------------------------------------------------------------

module "network" {
  source     = "../../modules/network"
  project_id = var.project_id
  region     = var.region

  network_name                        = var.vpc_network_name
  subnetwork_name                     = var.vpc_subnetwork_name
  subnetwork_cidr                     = var.vpc_subnetwork_cidr
  private_service_range_name          = var.private_service_range_name
  private_service_range_prefix_length = var.private_service_range_prefix_length

  depends_on = [module.project_services]
}

# ---------------------------------------------------------------------------
# 3. Secret Manager (empty shells — values loaded manually)
# ---------------------------------------------------------------------------

module "secret_manager" {
  source     = "../../modules/secret_manager"
  project_id = var.project_id

  secret_ids = [
    "jwt-secret-key",
    "service-account-json",
    "copilot-service-shared-jwt",
  ]

  labels = local.labels

  depends_on = [module.project_services]
}

# ---------------------------------------------------------------------------
# 4. Artifact Registry
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
# 5. Storage buckets (audio + frontend + cf source)
# ---------------------------------------------------------------------------

module "storage_buckets" {
  source                       = "../../modules/storage_buckets"
  project_id                   = var.project_id
  region                       = var.region
  audio_bucket_name            = var.audio_bucket_name
  frontend_bucket_name         = var.frontend_bucket_name
  cf_source_bucket_name        = var.cf_source_bucket
  frontend_public_read_enabled = var.frontend_public_read_enabled
  audio_retention_days         = 7
  force_destroy                = true
  labels                       = local.labels

  depends_on = [module.project_services]
}

# ---------------------------------------------------------------------------
# 6. Service accounts + IAM bindings
# ---------------------------------------------------------------------------

module "service_accounts" {
  source                                = "../../modules/service_accounts"
  project_id                            = var.project_id
  audio_bucket_name                     = module.storage_buckets.audio_bucket_name
  frontend_bucket_name                  = module.storage_buckets.frontend_bucket_name
  cf_source_bucket_name                 = module.storage_buckets.cf_source_bucket_name
  grant_cloud_functions_secret_accessor = false
  grant_copilot_agent_secret_accessor   = true

  depends_on = [
    module.project_services,
    module.storage_buckets,
  ]
}

# ---------------------------------------------------------------------------
# 7. Workload Identity Federation (GitHub Actions)
# ---------------------------------------------------------------------------

module "workload_identity" {
  source     = "../../modules/workload_identity"
  project_id = var.project_id

  github_repo          = var.github_repo
  service_account_name = module.service_accounts.github_actions_deployer_name
  allowed_refs         = ["refs/heads/main"]
  allowed_workflow_files = [
    ".github/workflows/backend-fastapi-deployment-stg.yaml",
    ".github/workflows/copilot-agent-deployment-stg.yaml",
    ".github/workflows/deploy-cloud-function-stg.yaml",
    ".github/workflows/frontend-deployment-stg.yaml",
    ".github/workflows/landing-page-deployment-stg.yaml",
  ]

  depends_on = [module.service_accounts]
}

# ---------------------------------------------------------------------------
# 8. Cloud SQL
# ---------------------------------------------------------------------------

module "cloud_sql" {
  source                    = "../../modules/cloud_sql"
  project_id                = var.project_id
  region                    = var.region
  instance_name             = var.db_instance_name
  tier                      = var.db_tier
  database_name             = var.db_name
  additional_database_names = [var.copilot_agent_db_name]
  ipv4_enabled              = false
  private_network           = module.network.network_id
  enable_iam_auth           = true
  iam_database_users = [
    module.service_accounts.backend_runner_email,
    module.service_accounts.copilot_agent_runner_email,
  ]

  deletion_protection = true

  depends_on = [
    module.project_services,
    module.network,
  ]
}

# ---------------------------------------------------------------------------
# 9. Cloud Tasks
# ---------------------------------------------------------------------------

module "cloud_tasks" {
  source     = "../../modules/cloud_tasks"
  project_id = var.project_id
  region     = var.region

  queue_name                = "audio-transcription-queue-stg"
  max_attempts              = 3
  max_concurrent_dispatches = 3
  min_backoff_seconds       = 10
  max_backoff_seconds       = 300

  depends_on = [module.project_services]
}

# ---------------------------------------------------------------------------
# 10. Cloud Run (backend)
# ---------------------------------------------------------------------------

module "cloud_run" {
  source     = "../../modules/cloud_run"
  project_id = var.project_id
  region     = var.region

  service_name              = var.cloud_run_service_name
  image                     = var.cloud_run_image
  service_account_email     = module.service_accounts.backend_runner_email
  cloud_sql_connection_name = module.cloud_sql.connection_name
  cloud_sql_volume_enabled  = false

  min_instances    = 0
  max_instances    = var.cloud_run_max_instances
  max_concurrency  = var.cloud_run_max_concurrency
  session_affinity = true

  env_vars = {
    ENVIRONMENT                         = var.environment
    GCP_PROJECT                         = var.project_id
    GOOGLE_CLOUD_PROJECT                = var.project_id
    GCP_PROJECT_ID                      = var.project_id
    GCS_BUCKET_NAME                     = module.storage_buckets.audio_bucket_name
    DB_HOST                             = "127.0.0.1"
    DB_PORT                             = "5432"
    DB_NAME                             = var.db_name
    DB_USER                             = trimsuffix(module.service_accounts.backend_runner_email, ".gserviceaccount.com")
    CLOUD_TASKS_REGION                  = var.region
    TRANSCRIPTION_QUEUE_NAME            = module.cloud_tasks.queue_name
    CLOUD_TASKS_INVOKER_SERVICE_ACCOUNT = module.service_accounts.cloud_tasks_invoker_email
  }

  secret_env_vars = var.cloud_run_use_secret_manager ? [
    { name = "JWT_SECRET_KEY", secret_id = "jwt-secret-key" },
    { name = "COPILOT_SERVICE_SHARED_JWT", secret_id = "copilot-service-shared-jwt" },
  ] : []

  vpc_access = {
    network    = module.network.network_name
    subnetwork = module.network.subnetwork_name
    egress     = "PRIVATE_RANGES_ONLY"
  }

  sidecars = [
    {
      name  = "cloud-sql-proxy"
      image = var.cloud_run_db_proxy_image
      args = [
        "--private-ip",
        "--auto-iam-authn",
        "--address=127.0.0.1",
        "--port=5432",
        module.cloud_sql.connection_name,
      ]
    },
  ]

  allow_unauthenticated = var.cloud_run_allow_unauthenticated
  labels                = local.labels

  depends_on = [
    module.service_accounts,
    module.cloud_sql,
    module.secret_manager,
  ]
}

# ---------------------------------------------------------------------------
# 10b. Cloud Run (copilot agent)
# ---------------------------------------------------------------------------

module "copilot_agent_cloud_run" {
  source     = "../../modules/cloud_run"
  project_id = var.project_id
  region     = var.region

  service_name              = var.copilot_agent_service_name
  image                     = var.copilot_agent_image
  service_account_email     = module.service_accounts.copilot_agent_runner_email
  cloud_sql_connection_name = module.cloud_sql.connection_name
  cloud_sql_volume_enabled  = false

  min_instances    = 0
  max_instances    = var.copilot_agent_max_instances
  max_concurrency  = var.copilot_agent_max_concurrency
  session_affinity = false
  container_port   = 8090

  env_vars = {
    COPILOT_AGENT_ENV              = var.environment
    COPILOT_AGENT_PORT             = "8090"
    COPILOT_AGENT_LOG_LEVEL        = "INFO"
    GCP_PROJECT_ID                 = var.project_id
    GOOGLE_CLOUD_PROJECT           = var.project_id
    GCP_REGION                     = var.region
    VERTEX_MODEL                   = "gemini-2.5-flash"
    BACKEND_INTERNAL_BASE_URL      = module.cloud_run.service_url
    COPILOT_ALLOWED_AUDIENCE       = "app-api-service"
    COPILOT_AGENT_DATABASE_URL     = "postgresql://127.0.0.1:5432/${var.copilot_agent_db_name}"
    COPILOT_LONG_TERM_DATABASE_URL = "postgresql://127.0.0.1:5432/${var.copilot_agent_db_name}"
  }

  secret_env_vars = var.cloud_run_use_secret_manager ? [
    { name = "COPILOT_SERVICE_SHARED_JWT", secret_id = "copilot-service-shared-jwt" },
  ] : []

  vpc_access = {
    network    = module.network.network_name
    subnetwork = module.network.subnetwork_name
    egress     = "PRIVATE_RANGES_ONLY"
  }

  sidecars = [
    {
      name  = "cloud-sql-proxy"
      image = var.cloud_run_db_proxy_image
      args = [
        "--private-ip",
        "--auto-iam-authn",
        "--address=127.0.0.1",
        "--port=5432",
        module.cloud_sql.connection_name,
      ]
    },
  ]

  allow_unauthenticated = var.copilot_agent_allow_unauthenticated
  labels                = local.labels

  depends_on = [
    module.service_accounts,
    module.cloud_sql,
    module.secret_manager,
  ]
}

# ---------------------------------------------------------------------------
# 11. Monitoring
# ---------------------------------------------------------------------------

module "monitoring" {
  source                 = "../../modules/monitoring"
  project_id             = var.project_id
  billing_account_name   = var.billing_account_name
  cloud_run_service_name = var.cloud_run_service_name
  cloud_function_service_names = [
    "transcription-endpoint",
    "document-workflow",
  ]
  cloud_sql_instance_name   = var.db_instance_name
  monthly_budget_amount_usd = var.monthly_budget_amount_usd

  depends_on = [
    module.project_services,
    module.cloud_run,
    module.copilot_agent_cloud_run,
    module.cloud_sql,
  ]
}
