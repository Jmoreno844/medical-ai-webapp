# =============================================================================
# Test environment (vex-stg) — fill in values before running terraform apply
# =============================================================================

project_id  = "vex-stg"
region      = "us-east1"
environment = "test"

# GitHub (owner/repo) — must match WIF attribute_condition in Terraform
github_repo = "Jmoreno844/medical-ai-webapp"

# Cloud SQL
db_instance_name = "vexthealth-db-test"
db_tier          = "db-f1-micro"
db_name          = "vexthealthdb"
db_user          = "appuser"
# db_password is sensitive — pass via env var TF_VAR_db_password or -var flag

# Cloud Run
cloud_run_service_name = "vexthealth-backend"
# Bootstrap with a public image; CI later replaces it with the app image.
cloud_run_image                 = "us-docker.pkg.dev/cloudrun/container/hello"
cloud_run_max_instances         = 1
cloud_run_max_concurrency       = 250
cloud_run_use_secret_manager    = true
cloud_run_allow_unauthenticated = true # Set false if org policy blocks allUsers on Cloud Run

# Cloud Functions source (deploy from GCS)
cf_source_bucket = "vex-stg-cf-source"   # TODO: create this bucket or use a deploy script
cf_source_object = "cloud-functions.zip" # TODO: zip and upload before first apply

# Storage buckets
audio_bucket_name            = "vex-stg-audio"
frontend_bucket_name         = "vex-stg-frontend-spa"
frontend_public_read_enabled = true # Set false if org policy blocks allUsers on GCS buckets

# Artifact Registry
artifact_registry_repo = "vexthealth-containers"
