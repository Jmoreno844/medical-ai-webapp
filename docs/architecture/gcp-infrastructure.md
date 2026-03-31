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

Después de `terraform apply`, configurar las mismas claves como **variables del environment `stg`** (recomendado) o como **repository variables**. Los workflows de deploy declaran `environment: stg` en los jobs que hablan con GCP, porque el contexto `vars.*` del workflow **no** incluye variables solo definidas en un environment.

| Variable | Valor (output de Terraform) |
|---|---|
| `GCP_PROJECT_ID` | `vex-stg` |
| `WIF_PROVIDER` | `projects/<num>/locations/global/workloadIdentityPools/github-actions-pool/providers/github-oidc-provider` |
| `GH_DEPLOYER_SA` | `github-actions-deployer@vex-stg.iam.gserviceaccount.com` |
| `BACKEND_SERVICE_ACCOUNT` | `backend-runner@vex-stg.iam.gserviceaccount.com` |
| `GCS_BUCKET_NAME` | `vex-stg-audio` |
| `FRONTEND_BUCKET_NAME` | `vex-stg-frontend-spa` |
| `VITE_API_URL` | URL de Cloud Run (output) |
| *(build)* `VITE_BASE_URL` | El workflow de frontend la deriva de `FRONTEND_BUCKET_NAME` (`/{bucket}/`) para que los assets carguen bajo `storage.googleapis.com/{bucket}/`. |
| `GENERATE_DOCUMENT_CLOUD_FUNCTION_URL` | URL de la CF `document-workflow` (output) |
| `TRANSCRIPTION_CLOUD_FUNCTION_URL` | URL de la CF `transcription-endpoint` (output) |
| `INSTANCE_CONNECTION_NAME` | Mismo valor que output Terraform `cloud_sql_connection_name` (p. ej. `vex-stg:us-east1:vexthealth-db-test`) para el socket `/cloudsql/...` en Cloud Run |
| `CF_SOURCE_BUCKET` | *(opcional)* Bucket del zip para Terraform; por defecto en CI: `{GCP_PROJECT_ID}-cf-source` (debe coincidir con `cf_source_bucket` en `terraform.tfvars`) |
| `CF_SOURCE_OBJECT` | *(opcional)* Objeto del zip; por defecto `cloud-functions.zip` (igual que `cf_source_object` en Terraform) |

El secret `GCP_SA_KEY` puede eliminarse una vez confirmado que WIF funciona.

### Zip del código de Cloud Functions en CI

El workflow [`.github/workflows/deploy-cloud-function.yaml`](../../.github/workflows/deploy-cloud-function.yaml) hace, en cada push a `main` que toque `cloud_functions/functions/`:

1. Crea `gs://{proyecto}-cf-source` si no existe (misma convención que `terraform.tfvars`).
2. Genera un zip del directorio `cloud_functions/functions/` (excluye `__pycache__`, `.venv`, etc.) y lo sube a `cloud-functions.zip`.
3. Despliega las dos funciones con `gcloud functions deploy` (origen local, igual que antes).

Así el artefacto en GCS queda alineado con lo que espera el módulo Terraform `cloud_functions` cuando ejecutes `terraform apply`. El deploy sigue siendo el de `gcloud` para no depender de un segundo pipeline solo de Terraform.

### Checklist: que los workflows no fallen

| Requisito | Workflows afectados |
|---|---|
| Variables `GCP_PROJECT_ID`, `WIF_PROVIDER`, `GH_DEPLOYER_SA` definidas y WIF creado en GCP | Backend, Cloud Functions, Frontend |
| `BACKEND_SERVICE_ACCOUNT`, `GCS_BUCKET_NAME`, URLs de CF, `VITE_API_URL`, `INSTANCE_CONNECTION_NAME` | Backend deploy |
| `FRONTEND_BUCKET_NAME` | Frontend deploy |
| SA `github-actions-deployer` con los roles del módulo Terraform (p. ej. `storage.admin`, `cloudfunctions.developer`) | Todos los despliegues |

## Problemas frecuentes

| Síntoma | Qué revisar |
|---|---|
| `Failed to generate Google Cloud access token` en Actions | Variables `WIF_PROVIDER` y `GH_DEPLOYER_SA`; en GCP, que el pool/provider existan y el binding `workloadIdentityUser` apunte al repo correcto (`terraform.tfvars` → `github_repo`). |
| Backend no conecta a Cloud SQL | Secret `db-user` / `db-name` / `db-password` en Secret Manager; que la contraseña coincida con el usuario creado por Terraform (`TF_VAR_db_password` en el apply). |
| Cloud Run / Django intenta `localhost:5432` | Falta `INSTANCE_CONNECTION_NAME` (env en Terraform y en variables del workflow `stg`); el backend debe usar host `/cloudsql/<connection_name>` (ver `config.settings.test`). |
| `password authentication failed for user "…"` | Los secretos `db-user` y `db-password` deben coincidir con el usuario creado por Terraform (`db_user` / `TF_VAR_db_password` del apply). Cargar versiones con `printf %s 'valor'` para evitar saltos de línea. |
| `terraform apply` bloqueado por state lock | Otro `plan`/`apply` colgado o Ctrl+C; `terraform force-unlock <id>` tras confirmar que no hay otro proceso usando el state. |
| Zip de Cloud Functions inválido en CI | No usar `mktemp … .zip` como destino de `zip` (archivo vacío previo); no usar exclusiones `**/` con `zip` en Ubuntu. El workflow ya usa ruta `$$` + patrones simples y `unzip -t`. |
| Assets del SPA en `storage.googleapis.com/assets/...` 404 | `Vite` con `base: '/'` rompe en bucket; el workflow define `VITE_BASE_URL` desde `FRONTEND_BUCKET_NAME` y el router usa `basename`. |
| Variables de GitHub vacías en Actions | Las variables solo en el environment `stg` no se ven en `env` a nivel workflow; los jobs de deploy deben tener `environment: stg` (ya aplicado en los workflows). |
| `403` al crear bucket / APIs | Facturación del proyecto activa; APIs habilitadas (`terraform` o bootstrap). |
| Terraform falla en Cloud Functions | Que exista `gs://{proyecto}-cf-source/cloud-functions.zip` (p. ej. tras un run del workflow Deploy Cloud Functions) o comenta el módulo hasta tener el zip. |
| Cloud Functions falla con `missing permission on the build service account` | Dar `roles/storage.objectViewer` al service account de build (`PROJECT_NUMBER-compute@developer.gserviceaccount.com`) sobre el bucket interno `gcf-v2-sources-*`; el módulo `service_accounts` ya contempla este binding para nuevos applies. |
| Cloud Functions falla porque la build SA no puede escribir logs | Dar `roles/logging.logWriter` a `PROJECT_NUMBER-compute@developer.gserviceaccount.com`; el módulo `service_accounts` ya contempla este binding para nuevos applies. |
| Cloud Functions falla con `artifactregistry.repositories.downloadArtifacts denied` | Dar `roles/artifactregistry.reader` y `roles/artifactregistry.writer` al service account de build `PROJECT_NUMBER-compute@developer.gserviceaccount.com`; el módulo `service_accounts` ya contempla estos bindings para nuevos applies. |
| Cloud Run falla con `Image ... not found` | Usar una imagen bootstrap publica en `cloud_run_image` para el primer `apply`, o publicar primero `django-backend:latest` en Artifact Registry. |
| Cloud Run falla porque `Secret ... versions/latest was not found` | En bootstrap, usar `cloud_run_use_secret_manager = false`; después de cargar versiones en Secret Manager, volver a `true` para que el backend lea secretos reales. |
| Cloud Run falla al aplicar IAM con `allUsers ... do not belong to a permitted customer` | La organizacion bloquea acceso publico; poner `cloud_run_allow_unauthenticated = false` y exponer el servicio luego mediante una estrategia compatible con tu tenant. |
| Bucket frontend falla con `allUsers ... do not belong to a permitted customer` | La organizacion bloquea buckets publicos; poner `frontend_public_read_enabled = false` y definir luego hosting/CDN alternativo si necesitas SPA publica. |

## Fuera de este documento (aún no en IaC)

- Dominio, certificado y load balancer para `app.vexthealth.com` (decisión explícita: fuera de alcance del Terraform actual).
- Reglas de firewall/VPC avanzadas si Cloud SQL pasa a solo IP privada sin acceso público.
- Alertas, SLOs y presupuestos en GCP (recomendable añadir en consola o Terraform más adelante).

## Cómo agregar el entorno de producción

1. Crear nuevo proyecto GCP
2. Ejecutar bootstrap (`infra/bootstrap/README.md`) apuntando al proyecto nuevo
3. Copiar `infra/environments/test/` a `infra/environments/prod/`
4. Editar `backend.tf` (bucket de estado) y `terraform.tfvars` (valores de prod)
5. `terraform init && terraform plan && terraform apply`
6. Configurar variables de GitHub para prod (o usar environments de GitHub)

Ver `infra/environments/prod/README.md` para diferencias específicas test vs prod.
