# Entorno de producción

Este directorio queda como placeholder hasta que se cree el proyecto de producción en GCP.

## Cómo crear el entorno prod

1. Copia todos los archivos de `../stg/` a esta carpeta:

```bash
cp ../stg/providers.tf .
cp ../stg/variables.tf .
cp ../stg/main.tf .
cp ../stg/outputs.tf .
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

cloud_run_service_name    = "vexthealth-backend"
cloud_run_image           = "us-east1-docker.pkg.dev/<PROD_PROJECT_ID>/vexthealth-containers/fastapi-backend:latest"
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
terraform plan
terraform apply
```

## Diferencias clave respecto a stg

| Aspecto | Stg | Prod |
|---|---|---|
| Cloud SQL tier | `db-f1-micro` | `db-custom-1-3840` o superior |
| Cloud SQL deletion_protection | `true` | `true` |
| Cloud Run min_instances | `0` | `1` (cold start eliminado) |
| Storage force_destroy | `true` | `false` |
| Backups PITR | no (f1-micro) | sí |
| ALLOWED_HOSTS | `["*"]` | solo dominios reales |

## Notas para no heredar defaults peligrosos

- Mantén la red privada como patrón por defecto: Cloud SQL por IP privada y Cloud Run con egress privado.
- No reintroduzcas `force_destroy = true` en buckets de prod.
- No asumas una imagen bootstrap pública en prod.
- El edge público duro (HTTPS Load Balancer, certificado administrado y opcionalmente Cloud Armor) sigue siendo una capa posterior al alcance actual de `stg`.
