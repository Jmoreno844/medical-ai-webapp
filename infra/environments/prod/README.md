# Entorno de producción

Este directorio queda como placeholder hasta que se cree el proyecto de producción en GCP.

## Cómo crear el entorno prod

1. Copia todos los archivos de `../test/` a esta carpeta:

```bash
cp ../test/providers.tf .
cp ../test/variables.tf .
cp ../test/main.tf .
cp ../test/outputs.tf .
```

2. Crea `backend.tf` apuntando al bucket de estado de prod:

```hcl
terraform {
  backend "gcs" {
    bucket = "<PROD_PROJECT_ID>-terraform-state"
    prefix = "terraform/prod"
  }
}
```

3. Crea `terraform.tfvars` con los valores de producción:

```hcl
project_id  = "<PROD_PROJECT_ID>"
region      = "us-east1"
environment = "prod"

github_repo = "OWNER/your-repo"

db_instance_name = "vexthealth-db-prod"
db_tier          = "db-custom-1-3840"  # 1 vCPU, 3.75 GB RAM
db_name          = "vexthealthdb"
db_user          = "appuser"

cloud_run_service_name    = "vexthealth-backend"
cloud_run_image           = "us-east1-docker.pkg.dev/<PROD_PROJECT_ID>/vexthealth-containers/django-backend:latest"
cloud_run_max_instances   = 1       # Mantener en 1 por SSE en memoria (ver ADR-0002)
cloud_run_max_concurrency = 250

cf_source_bucket = "<PROD_PROJECT_ID>-cf-source"
cf_source_object = "cloud-functions.zip"

audio_bucket_name    = "<PROD_PROJECT_ID>-audio"
frontend_bucket_name = "<PROD_PROJECT_ID>-frontend-spa"

artifact_registry_repo = "vexthealth-containers"
```

4. Ejecuta el bootstrap del proyecto nuevo siguiendo `infra/bootstrap/README.md` (cambiando `PROJECT_ID`).

5. Inicializa y aplica:

```bash
terraform init
terraform plan -var="db_password=<PASSWORD>"
terraform apply -var="db_password=<PASSWORD>"
```

## Diferencias clave respecto a test

| Aspecto | Test | Prod |
|---|---|---|
| Cloud SQL tier | `db-f1-micro` | `db-custom-1-3840` o superior |
| Cloud SQL deletion_protection | `true` | `true` |
| Cloud Run min_instances | `0` | `1` (cold start eliminado) |
| Storage force_destroy | `true` | `false` |
| Backups PITR | no (f1-micro) | sí |
| ALLOWED_HOSTS | `["*"]` | solo dominios reales |
