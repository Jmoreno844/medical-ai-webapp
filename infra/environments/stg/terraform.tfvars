# =============================================================================
# Staging environment (vext-stg) — fill in values before running terraform apply
# =============================================================================

project_id           = "vext-stg"
region               = "us-east1"
environment          = "stg"
billing_account_name = "billingAccounts/01C163-A52891-471F1D"

# GitHub (owner/repo) — must match WIF attribute_condition in Terraform
github_repo = "Jmoreno844/medical-ai-webapp"

# Cloud SQL
db_instance_name      = "vexthealth-db-stg"
db_tier               = "db-f1-micro"
db_name               = "vext-stg"
copilot_agent_db_name = "vext-stg-copilot"

# Cloud Run
cloud_run_service_name                  = "vexthealth-backend"
copilot_agent_service_name              = "vexthealth-copilot-agent"
frontend_service_name                   = "vexthealth-frontend"
transcription_worker_service_name       = "vexthealth-transcription-worker"
document_generation_worker_service_name = "vexthealth-document-generation-worker"
admin_bootstrap_job_name                = "vexthealth-backend-admin-bootstrap"
# Bootstrap with a public image; CI later replaces it with the app image.
cloud_run_image                            = "us-docker.pkg.dev/cloudrun/container/hello"
copilot_agent_image                        = "us-docker.pkg.dev/cloudrun/container/hello"
frontend_image                             = "us-docker.pkg.dev/cloudrun/container/hello"
transcription_worker_image                 = "us-docker.pkg.dev/cloudrun/container/hello"
document_generation_worker_image           = "us-docker.pkg.dev/cloudrun/container/hello"
cloud_run_max_instances                    = 1
cloud_run_max_concurrency                  = 250
copilot_agent_max_instances                = 2
copilot_agent_max_concurrency              = 20
frontend_max_instances                     = 3
frontend_max_concurrency                   = 80
transcription_worker_max_instances         = 5
transcription_worker_max_concurrency       = 8
document_generation_worker_max_instances   = 5
document_generation_worker_max_concurrency = 8
cloud_run_use_secret_manager               = true
cloud_run_allow_unauthenticated            = true # Set false if org policy blocks allUsers on Cloud Run
copilot_agent_allow_unauthenticated        = false

# Storage buckets
audio_bucket_name            = "vext-stg-audio"
frontend_bucket_name         = "vext-stg-frontend-spa"
frontend_public_read_enabled = false
frontend_domain_name         = "app-stg.notiahealth.com"
backend_domain_name          = "api-stg.notiahealth.com"
fastapi_cors_allowed_origins = "https://app-stg.notiahealth.com"
gemini_model                 = "gemini-3.1-flash-lite-preview"

#Document Generation Worker 
document_generation_provider    ="google_vertex"

# Artifact Registry
artifact_registry_repo = "vexthealth-containers"
