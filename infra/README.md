# Infraestructura (Terraform)

Gestiona todos los recursos GCP de VexHealth. Cada entorno (`test`, `prod`) tiene su propio directorio con `terraform.tfvars` y backend de estado separado.

## Estructura

```
infra/
  bootstrap/          # Pasos manuales (una sola vez por proyecto GCP)
  modules/            # Módulos reutilizables
    project_services/   APIs de GCP
    service_accounts/   SAs + IAM bindings
    secret_manager/     Shells de secrets (sin valores)
    artifact_registry/  Repositorio Docker
    cloud_sql/          PostgreSQL
    storage_buckets/    Audio + frontend SPA
    cloud_run/          Backend Django
    cloud_functions/    Transcripción + generación
    cloud_tasks/        Cola de transcripción
    workload_identity/  WIF para GitHub Actions
  environments/
    test/               vex-stg
    prod/               (placeholder)
```

## Requisitos previos

- [Terraform >= 1.5](https://developer.hashicorp.com/terraform/install)
- `gcloud` CLI autenticado con permisos sobre el proyecto
- Haber completado el bootstrap (`bootstrap/README.md`)

## Flujo de trabajo

### 1. Bootstrap (una sola vez por proyecto)

```bash
cd infra/bootstrap
# Seguir instrucciones de README.md
```

### 2. Inicializar

```bash
cd infra/environments/test
terraform init
```

### 3. Plan

```bash
terraform plan -var="db_password=<PASSWORD>"
```

Siempre revisar el plan antes de aplicar. Buscar destrucción accidental de recursos.

### 4. Aplicar

```bash
terraform apply -var="db_password=<PASSWORD>"
```

### 5. Obtener outputs

```bash
terraform output
```

Los outputs incluyen URLs de Cloud Run, Cloud Functions, service account emails y el WIF provider path necesario para configurar GitHub.

## Variables sensibles

| Variable | Cómo pasarla |
|---|---|
| `db_password` | `-var="db_password=..."` o `TF_VAR_db_password` en env |

**Nunca** guardes passwords en `terraform.tfvars` ni en el state. El state debe estar en un bucket GCS privado con versionado habilitado.

## Agregar un entorno nuevo (e.g. prod)

1. Crear proyecto GCP y ejecutar el bootstrap
2. Copiar `environments/test/` a `environments/prod/`
3. Editar `backend.tf` con el bucket de estado del nuevo proyecto
4. Editar `terraform.tfvars` con los valores del nuevo proyecto
5. `terraform init && terraform plan && terraform apply`

Ver `environments/prod/README.md` para diferencias específicas.

## Cargar secrets manualmente

Terraform solo crea los recursos de Secret Manager vacíos. Para cargar valores:

```bash
echo -n "tu-valor" | gcloud secrets versions add django-secret-key --data-file=- --project=vex-stg
```

Repetir para cada secret: `jwt-secret-key`, `db-password`, `db-user`, `db-name`, `service-account-json`.

## Configurar GitHub después de terraform apply

Después del primer apply exitoso, copiar los outputs de Terraform a **repository variables** en GitHub Settings:

- `GCP_PROJECT_ID`
- `WIF_PROVIDER` (output `workload_identity_provider`)
- `GH_DEPLOYER_SA` (output `github_actions_deployer_email`)
- `BACKEND_SERVICE_ACCOUNT` (output `backend_service_account`)
- `GCS_BUCKET_NAME` (output `audio_bucket`)
- `FRONTEND_BUCKET_NAME` (output `frontend_bucket`)
- `VITE_API_URL` (output `cloud_run_url`)
- `GENERATE_DOCUMENT_CLOUD_FUNCTION_URL`
- `TRANSCRIPTION_CLOUD_FUNCTION_URL`

Luego se puede eliminar el secret `GCP_SA_KEY` de GitHub.

## Documentación relacionada

- `bootstrap/README.md` — comandos `gcloud` para el bootstrap inicial
- `docs/architecture/gcp-infrastructure.md` — matriz IAM, secrets, lifecycle, naming
- `docs/decisions/0002-notificaciones-en-tiempo-real-sse-en-memoria.md` — por qué `max-instances=1`
