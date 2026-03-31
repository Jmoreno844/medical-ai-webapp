# Infraestructura GCP

Referencia permanente de todos los recursos GCP gestionados por Terraform.  
IaC: `infra/` en la raíz del repo.

## Proyectos y regiones

| Entorno | Project ID | Región |
|---|---|---|
| Test | `vex-stg` | `us-east1` |
| Prod | *(por crear)* | `us-east1` |

## Convenciones de nombres

| Recurso | Patrón | Ejemplo (test) |
|---|---|---|
| Cloud Run service | `vexthealth-backend` | `vexthealth-backend` |
| Cloud Function | `<nombre-funcional>` | `transcription-endpoint`, `document-workflow` |
| Cloud SQL instance | `vexthealth-db-<env>` | `vexthealth-db-test` |
| GCS audio | `<project>-audio` | `vex-stg-audio` |
| GCS frontend | `<project>-frontend-spa` | `vex-stg-frontend-spa` |
| Artifact Registry | `vexthealth-containers` | `vexthealth-containers` |
| Cloud Tasks queue | `audio-transcription-queue` | `audio-transcription-queue` |
| Service accounts | `<rol>@<project>.iam` | `backend-runner@vex-stg.iam.gserviceaccount.com` |
| Terraform state | `<project>-terraform-state` | `vex-stg-terraform-state` |

## Matriz IAM (service accounts)

### backend-runner (Cloud Run)

| Rol | Justificación |
|---|---|
| `roles/cloudsql.client` | Conexión a Cloud SQL vía socket Unix |
| `roles/secretmanager.secretAccessor` | Leer secrets montados como env vars |
| `roles/storage.objectAdmin` | Subir/firmar URLs de audio en GCS |
| `roles/cloudtrace.agent` | Enviar trazas a Cloud Trace |
| `roles/cloudtasks.enqueuer` | Encolar tareas de transcripción |

### cloud-functions-runner (Cloud Functions)

| Rol | Justificación |
|---|---|
| `roles/aiplatform.user` | Llamar a Gemini/Vertex AI |
| `roles/storage.objectViewer` | Leer audio de GCS |
| `roles/secretmanager.secretAccessor` | Leer secrets (JWT, etc.) |
| `roles/cloudtrace.agent` | Enviar trazas a Cloud Trace |
| `roles/run.invoker` | Callback a Cloud Run si es necesario |

### cloud-tasks-invoker

| Rol | Justificación |
|---|---|
| `roles/cloudfunctions.invoker` | Invocar la Cloud Function de transcripción (binding por función) |
| `roles/run.invoker` | Invocar el servicio Cloud Run subyacente de la CF gen2 |

### github-actions-deployer (CI/CD via WIF)

| Rol | Justificación |
|---|---|
| `roles/run.admin` | Desplegar Cloud Run |
| `roles/cloudfunctions.developer` | Desplegar Cloud Functions |
| `roles/storage.admin` | Subir frontend a GCS |
| `roles/artifactregistry.writer` | Pushear imágenes Docker |
| `roles/iam.serviceAccountUser` | Actuar como otros SAs al desplegar |

## Secret Manager

Terraform crea las *resources* vacías. Los valores se cargan manualmente con `gcloud`:

```bash
echo -n "VALOR" | gcloud secrets versions add SECRET_ID --data-file=-
```

| Secret ID | Usado por | Descripción |
|---|---|---|
| `django-secret-key` | Cloud Run | Django `SECRET_KEY` |
| `jwt-secret-key` | Cloud Run | Firmado de JWTs (SSE, service) |
| `db-password` | Cloud Run | Password de Cloud SQL |
| `db-user` | Cloud Run | Usuario de Cloud SQL |
| `db-name` | Cloud Run | Nombre de la DB |
| `service-account-json` | Cloud Run | SA key para signed URLs de GCS |

### Rotación de secrets

1. Crear nueva versión: `gcloud secrets versions add <id> --data-file=-`
2. Redesplegar Cloud Run para que tome la nueva versión `latest`
3. Deshabilitar la versión anterior: `gcloud secrets versions disable <version> --secret=<id>`

## Políticas de ciclo de vida (GCS)

| Bucket | Regla | Detalle |
|---|---|---|
| `*-audio` | Delete after 7 days | Audio `.webm`/`.mp4` se elimina automáticamente |
| `*-frontend-spa` | Ninguna | Los archivos se sobreescriben en cada deploy |

## Cloud Tasks

| Queue | Max attempts | Min backoff | Max backoff | Target |
|---|---|---|---|---|
| `audio-transcription-queue` | 3 | 10s | 300s | `transcription-endpoint` (CF) |

## Cloud Run — configuración clave

| Parámetro | Valor (test) | Nota |
|---|---|---|
| `max-instances` | 1 | **Obligatorio** por SSE en memoria (ver ADR-0002) |
| `max-concurrency` | 250 | Capacidad del ASGI server |
| `session-affinity` | true | Necesario para SSE |
| `min-instances` | 0 (test), 1 (prod) | Evitar cold start en prod |

## Cloud Functions — IAM auth

Ambas funciones (`transcription-endpoint`, `document-workflow`) están desplegadas con `--no-allow-unauthenticated`.

Solo las service accounts autorizadas pueden invocarlas:

- `transcription-endpoint` ← `cloud-tasks-invoker` (vía Cloud Tasks)
- `document-workflow` ← `backend-runner` (HTTP directo desde Cloud Run)

## Workload Identity Federation

Elimina la necesidad de claves JSON (`GCP_SA_KEY`) en GitHub Actions.

| Componente | Valor |
|---|---|
| Pool | `github-actions-pool` |
| Provider | `github-oidc-provider` |
| Issuer | `https://token.actions.githubusercontent.com` |
| Attribute condition | `assertion.repository == "Jmoreno844/medical-ai-webapp"` (ajustar en `terraform.tfvars` si el repo cambia) |
| SA impersonada | `github-actions-deployer@<project>.iam.gserviceaccount.com` |

### Variables requeridas en GitHub

Después de `terraform apply`, configurar estas **repository variables** en GitHub:

| Variable | Valor (output de Terraform) |
|---|---|
| `GCP_PROJECT_ID` | `vex-stg` |
| `WIF_PROVIDER` | `projects/<num>/locations/global/workloadIdentityPools/github-actions-pool/providers/github-oidc-provider` |
| `GH_DEPLOYER_SA` | `github-actions-deployer@vex-stg.iam.gserviceaccount.com` |
| `BACKEND_SERVICE_ACCOUNT` | `backend-runner@vex-stg.iam.gserviceaccount.com` |
| `GCS_BUCKET_NAME` | `vex-stg-audio` |
| `FRONTEND_BUCKET_NAME` | `vex-stg-frontend-spa` |
| `VITE_API_URL` | URL de Cloud Run (output) |
| `GENERATE_DOCUMENT_CLOUD_FUNCTION_URL` | URL de la CF `document-workflow` (output) |
| `TRANSCRIPTION_CLOUD_FUNCTION_URL` | URL de la CF `transcription-endpoint` (output) |

El secret `GCP_SA_KEY` puede eliminarse una vez confirmado que WIF funciona.

## Cómo agregar el entorno de producción

1. Crear nuevo proyecto GCP
2. Ejecutar bootstrap (`infra/bootstrap/README.md`) apuntando al proyecto nuevo
3. Copiar `infra/environments/test/` a `infra/environments/prod/`
4. Editar `backend.tf` (bucket de estado) y `terraform.tfvars` (valores de prod)
5. `terraform init && terraform plan && terraform apply`
6. Configurar variables de GitHub para prod (o usar environments de GitHub)

Ver `infra/environments/prod/README.md` para diferencias específicas test vs prod.
