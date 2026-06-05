# Infraestructura GCP

Referencia permanente de todos los recursos GCP gestionados por Terraform.  
IaC: `infra/` en la raíz del repo.

## Proyectos y regiones

| Entorno | Project ID    | Región     |
| ------- | ------------- | ---------- |
| Staging | `vext-stg`    | `us-east1` |
| Prod    | _(por crear)_ | `us-east1` |

## Convenciones de nombres

| Recurso            | Patrón                          | Ejemplo (stg)                                     |
| ------------------ | ------------------------------- | ------------------------------------------------- |
| Cloud Run service  | `vexthealth-backend`            | `vexthealth-backend`                              |
| Cloud Run job      | `vexthealth-backend-admin-bootstrap` | `vexthealth-backend-admin-bootstrap`        |
| Cloud Run service  | `vexthealth-frontend`           | `vexthealth-frontend`                             |
| Cloud Run copilot  | `vexthealth-copilot-agent`      | `vexthealth-copilot-agent`                        |
| Cloud Run worker   | `vexthealth-transcription-worker` | `vexthealth-transcription-worker`               |
| Cloud Run worker   | `vexthealth-document-generation-worker` | `vexthealth-document-generation-worker`   |
| Cloud SQL instance | `vexthealth-db-<env>`           | `vexthealth-db-stg`                               |
| GCS audio          | `<project>-audio`               | `vext-stg-audio`                                  |
| GCS frontend       | `<project>-frontend-spa`        | `vext-stg-frontend-spa`                           |
| Artifact Registry  | `vexthealth-containers`         | `vexthealth-containers`                           |
| Cloud Tasks queue  | `audio-transcription-queue-stg` | `audio-transcription-queue-stg`                   |
| Service accounts   | `<rol>@<project>.iam`           | `backend-runner@vext-stg.iam.gserviceaccount.com` |
| Terraform state    | `<project>-terraform-state`     | `vext-stg-terraform-state`                        |

## Matriz IAM (service accounts)

### backend-runner (Cloud Run)

| Rol                                                                | Justificación                                                    |
| ------------------------------------------------------------------ | ---------------------------------------------------------------- |
| `roles/cloudsql.client`                                            | Conexión vía Cloud SQL Auth Proxy                                |
| `roles/cloudsql.instanceUser`                                      | IAM DB auth contra Cloud SQL                                     |
| `roles/secretmanager.secretAccessor`                               | Leer secrets montados como env vars                              |
| `roles/storage.objectAdmin` sobre `*-audio`                        | Subir/firmar URLs de audio en GCS                                |
| `roles/cloudtrace.agent`                                           | Enviar trazas a Cloud Trace                                      |
| `roles/cloudtasks.enqueuer`                                        | Encolar tareas de transcripción y generación documental          |
| `roles/run.invoker`                                                | Invocar el copilot agent service por contrato interno            |
| `roles/iam.serviceAccountUser` sobre `cloud-tasks-invoker`         | Crear tasks autenticadas con OIDC                                |
| `roles/iam.serviceAccountTokenCreator` sobre `cloud-tasks-invoker` | Permitir que Cloud Tasks use la identidad del invoker SA         |

### copilot-agent-runner (Cloud Run)

| Rol                                  | Justificación                     |
| ------------------------------------ | --------------------------------- |
| `roles/cloudsql.client`              | Conexión vía Cloud SQL Auth Proxy |
| `roles/cloudsql.instanceUser`        | IAM DB auth contra Cloud SQL      |
| `roles/aiplatform.user`              | Llamar a Gemini/Vertex AI         |
| `roles/secretmanager.secretAccessor` | Leer secret compartido del broker |
| `roles/cloudtrace.agent`             | Enviar trazas a Cloud Trace       |

### transcription-worker-runner (Cloud Run)

| Rol                                                        | Justificación                                        |
| ---------------------------------------------------------- | ---------------------------------------------------- |
| `roles/storage.objectViewer` sobre `*-audio`               | Leer secciones de audio desde GCS                    |
| `roles/aiplatform.user`                                    | Llamar Gemini para transcripción por sección         |
| `roles/cloudtrace.agent`                                   | Enviar trazas saneadas a Cloud Trace                 |
| `roles/run.invoker`                                        | Llamar callbacks internos del backend FastAPI        |

### document-generation-runner (Cloud Run)

| Rol                                  | Justificación                                  |
| ------------------------------------ | ---------------------------------------------- |
| `roles/aiplatform.user`              | Llamar Vertex AI cuando el provider del worker usa Google o Anthropic via Vertex |
| `roles/cloudtrace.agent`             | Enviar trazas saneadas a Cloud Trace           |
| `roles/run.invoker`                  | Pedir work-items internos al backend FastAPI   |
| `roles/secretmanager.secretAccessor` | Leer LangSmith y `anthropic-api-key` si se usan en stg |

Para cumplimiento operativo, restringe `roles/logging.viewer` y
`roles/cloudtrace.user` al grupo mínimo de soporte necesario. Si en el futuro
algún bucket de logs almacenara campos sensibles, evaluar `field-level access`
antes de ampliar accesos.

### cloud-tasks-invoker

| Rol                 | Justificación                                                             |
| ------------------- | ------------------------------------------------------------------------- |
| `roles/run.invoker` | Invocar workers privados en Cloud Run vía Cloud Tasks |

### github-actions-deployer (CI/CD via WIF)

| Rol                                                                              | Justificación                           |
| -------------------------------------------------------------------------------- | --------------------------------------- |
| `roles/run.admin`                                                                | Desplegar Cloud Run                     |
| `roles/artifactregistry.writer`                                                  | Pushear imágenes Docker                 |
| `roles/storage.objectAdmin` sobre buckets de frontend                            | Subir assets de frontend                |
| `roles/iam.serviceAccountUser` sobre `backend-runner`                            | Actuar como otros SAs al desplegar      |

## Secret Manager

Terraform crea las _resources_ vacías. Los valores se cargan manualmente con `gcloud`:

```bash
echo -n "VALOR" | gcloud secrets versions add SECRET_ID --data-file=-
```

| Secret ID                    | Usado por               | Descripción                                                 |
| ---------------------------- | ----------------------- | ----------------------------------------------------------- |
| `jwt-secret-key`             | Cloud Run               | Firmado de JWTs (SSE, service)                              |
| `audit-ip-hmac-secret`       | Backend + admin job     | HMAC para pseudonimizar IPs del audit trail                 |
| `audit-ip-encryption-key`    | Backend + admin job     | Clave Fernet para IP cifrada en eventos de seguridad        |
| `service-account-json`       | Cloud Run               | Opcional; solo si se fuerza una SA key en lugar de ADC      |
| `copilot-service-shared-jwt` | Backend + Copilot Agent | JWT compartido para broker interno FastAPI -> agent runtime |
| `admin-bootstrap-password`   | Admin bootstrap job     | Password temporal leído por `ADMIN_BOOTSTRAP_PASSWORD`      |
| `anthropic-api-key`          | Document Worker         | Opcional; requerido si el worker usa `DOCUMENT_GENERATION_PROVIDER=anthropic_api` |
| `langsmith-api-key`          | Document Worker         | Opcional; necesario si se activa LangSmith en stg           |

Ni Terraform ni GitHub Actions cargan valores dentro de Secret Manager. Terraform
crea los secretos vacíos; los workflows y Cloud Run solo **referencian** esos
secretos por nombre/versión.

### Rotación de secrets

1. Crear nueva versión: `gcloud secrets versions add <id> --data-file=-`
2. Redesplegar Cloud Run para que tome la nueva versión `latest`
3. Deshabilitar la versión anterior: `gcloud secrets versions disable <version> --secret=<id>`

## Logging y retención

- Los logs de aplicación del backend y workers deben permanecer metadata-only.
- Definir retención explícita del bucket de logs de aplicación en vez de dejar
  el valor por defecto sin revisión operativa.
- Observabilidad y auditoría clínica son concerns distintos; no usar Cloud
  Logging como sustituto de un audit trail funcional.

## Políticas de ciclo de vida (GCS)

| Bucket           | Regla               | Detalle                                         |
| ---------------- | ------------------- | ----------------------------------------------- |
| `*-audio`        | Delete after 7 days | Audio `.webm`/`.mp4` se elimina automáticamente |
| `*-frontend-spa` | Ninguna             | Los archivos se sobreescriben en cada deploy    |

El bucket `*-audio` también necesita CORS para subida directa desde el navegador vía signed URL. En local se permiten `http://localhost:3000`, `http://127.0.0.1:3000`, `http://localhost:5173` y `http://127.0.0.1:5173` con métodos `PUT`, `GET`, `HEAD`, `OPTIONS` y `DELETE`.

## Cloud Tasks

| Queue                           | Max attempts | Min backoff | Max backoff | Target                                                                            |
| ------------------------------- | ------------ | ----------- | ----------- | --------------------------------------------------------------------------------- |
| `audio-transcription-queue-stg` | 3            | 10s         | 300s        | `transcription-worker` Cloud Run (OIDC con `cloud-tasks-invoker`) |
| `document-generation-queue-stg` | 3            | 10s         | 300s        | `document-generation-worker` Cloud Run (OIDC con `cloud-tasks-invoker`) |

## Cloud Run — configuración clave

| Parámetro          | Valor (stg)              | Nota                                              |
| ------------------ | ------------------------ | ------------------------------------------------- |
| `max-instances`    | 1                        | **Obligatorio** por SSE en memoria (ver ADR-0002) |
| `max-concurrency`  | 250                      | Capacidad del ASGI server                         |
| `session-affinity` | true                     | Necesario para SSE                                |
| `min-instances`    | 0 (stg), 1 (prod)        | Evitar cold start en prod                         |
| `ingress`          | `all`                    | La SPA sigue llamando directo a Cloud Run         |
| `vpc-egress`       | `PRIVATE_RANGES_ONLY`    | Solo la base de datos viaja por VPC               |
| `Cloud SQL`        | Private IP + IAM DB auth | PostgreSQL no queda expuesto por IP pública       |

La API FastAPI conserva esta restricción: no se introduce Redis/Memorystore
todavía, por lo que cualquier servicio que maneje SSE debe desplegarse con una sola instancia y afinidad de
sesión hasta que exista un broker compartido.

### Admin Bootstrap Cloud Run Job

- Job: `vexthealth-backend-admin-bootstrap`
- Usa la misma base de imagen del backend FastAPI
- Usa `backend-runner` y el mismo acceso a Cloud SQL / Secret Manager
- Ejecuta `python scripts/create_admin.py`
- El password de creación/reset viaja por `ADMIN_BOOTSTRAP_PASSWORD` montado
  desde Secret Manager, nunca por GitHub vars ni args de CLI

### Copilot Agent Cloud Run — configuración inicial

| Parámetro               | Valor (stg)                  | Nota                                    |
| ----------------------- | ---------------------------- | --------------------------------------- |
| `allow-unauthenticated` | `false`                      | No es un endpoint público               |
| `max-instances`         | 2                            | Runtime separado del backend            |
| `max-concurrency`       | 20                           | Más bajo por carga del grafo            |
| `session-affinity`      | `false`                      | No depende del hub SSE actual           |
| `Cloud SQL`             | misma instancia, DB separada | Checkpoints y memoria lógica del agente |

### Transcription Worker Cloud Run — configuración inicial

| Parámetro               | Valor (stg)                     | Nota                                                  |
| ----------------------- | ------------------------------- | ----------------------------------------------------- |
| `allow-unauthenticated` | `false`                         | Solo Cloud Tasks invoca endpoints de trabajo          |
| `max-instances`         | `5`                             | Escala independiente del backend con SSE en memoria   |
| `max-concurrency`       | `8`                             | El worker además limita VAD/Gemini con semáforos      |
| `cpu` / `memory`        | `2 vCPU` / `1Gi`                | Silero ONNX usa `ORT_INTRA_OP_NUM_THREADS=1`          |
| `session-affinity`      | `false`                         | No mantiene estado por cliente                        |
| `Cloud SQL`             | No                              | FastAPI conserva la autoridad de base de datos        |

### Document Generation Worker Cloud Run — configuración inicial

| Parámetro               | Valor (stg)                     | Nota                                                  |
| ----------------------- | ------------------------------- | ----------------------------------------------------- |
| `allow-unauthenticated` | `false`                         | Solo Cloud Tasks invoca endpoints de trabajo          |
| `max-instances`         | `5`                             | Escala independiente del backend con SSE en memoria   |
| `max-concurrency`       | `8`                             | El streaming LLM se limita además con semáforo        |
| `cpu` / `memory`        | `1 vCPU` / `1Gi`                | Sin dependencias de audio/ONNX                        |
| `session-affinity`      | `false`                         | No mantiene estado por cliente                        |
| `Cloud SQL`             | No                              | FastAPI conserva la autoridad de base de datos        |

## Workload Identity Federation

Elimina la necesidad de claves JSON (`GCP_SA_KEY`) en GitHub Actions.

| Componente          | Valor                                                       |
| ------------------- | ----------------------------------------------------------- |
| Pool                | `github-actions-pool`                                       |
| Provider            | `github-oidc-provider`                                      |
| Issuer              | `https://token.actions.githubusercontent.com`               |
| Attribute condition | Repo + `refs/heads/main` + workflows `*-stg.yaml`           |
| SA impersonada      | `github-actions-deployer@<project>.iam.gserviceaccount.com` |

### Variables requeridas en GitHub

Después de `terraform apply`, configurar las mismas claves como **variables del environment `stg`** (recomendado) o como **repository variables**. Los workflows de deploy declaran `environment: stg` en los jobs que hablan con GCP, porque el contexto `vars.*` del workflow **no** incluye variables solo definidas en un environment.

| Variable                        | Valor (output de Terraform)                                                                                                                     |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `GCP_PROJECT_ID`                | `vext-stg`                                                                                                                                      |
| `WIF_PROVIDER`                  | `projects/<num>/locations/global/workloadIdentityPools/github-actions-pool/providers/github-oidc-provider`                                      |
| `GH_DEPLOYER_SA`                | `github-actions-deployer@vext-stg.iam.gserviceaccount.com`                                                                                      |
| `BACKEND_SERVICE_ACCOUNT`       | `backend-runner@vext-stg.iam.gserviceaccount.com`                                                                                               |
| `FASTAPI_CORS_ALLOWED_ORIGINS`  | `https://app-stg.notiahealth.com`                                                                                                                |
| `FRONTEND_SERVICE_ACCOUNT`      | `frontend-runner@vext-stg.iam.gserviceaccount.com`                                                                                              |
| `COPILOT_AGENT_SERVICE_ACCOUNT` | `copilot-agent-runner@vext-stg.iam.gserviceaccount.com`                                                                                         |
| `TRANSCRIPTION_WORKER_SERVICE_ACCOUNT` | `transcription-worker-runner@vext-stg.iam.gserviceaccount.com`                                                                           |
| `DOCUMENT_GENERATION_WORKER_SERVICE_ACCOUNT` | `document-generation-runner@vext-stg.iam.gserviceaccount.com`                                                                    |
| `COPILOT_AGENT_DB_NAME`         | `vext-stg-copilot`                                                                                                                              |
| `GCS_BUCKET_NAME`               | `vext-stg-audio`                                                                                                                                |
| `FRONTEND_BUCKET_NAME`          | `vext-stg-frontend-spa`                                                                                                                         |
| `VITE_API_URL`                  | Para `stg`, usar el subdominio del backend, por ejemplo `https://api-stg.notiahealth.com`.                                                   |
| `COPILOT_AGENT_URL`             | URL del copilot agent service (output)                                                                                                          |
| `ADMIN_BOOTSTRAP_JOB_NAME`      | _(opcional)_ Si quieres documentarlo en GitHub vars; por defecto `vexthealth-backend-admin-bootstrap`                                          |
| `TRANSCRIPTION_WORKER_URL`      | URL del transcription worker Cloud Run (output `transcription_worker_cloud_run_url`)                                                            |
| `DOCUMENT_GENERATION_WORKER_URL` | URL del document generation worker Cloud Run (output `document_generation_worker_cloud_run_url`)                                                 |
| _(build)_ `VITE_BASE_URL`       | El workflow de frontend la fija en `/`, porque el frontend Cloud Run sirve la SPA desde la raiz de su propio subdominio.                      |
| `LANDING_BUCKET_NAME`           | Bucket del workflow de landing page si se usa ese deploy                                                                                        |
| `DOCUMENT_GENERATION_PROVIDER`  | _(opcional)_ Provider del worker; por defecto `anthropic_api`                                                                                   |
| `DOCUMENT_GENERATION_MODEL`     | _(opcional)_ Override explícito del modelo del worker                                                                                            |
| `DOCUMENT_GENERATION_ANTHROPIC_MODEL` | _(opcional)_ Fallback para Anthropic; por defecto `claude-haiku-4-5-20251001`                                                           |
| `DOCUMENT_GENERATION_GOOGLE_MODEL` | _(opcional)_ Fallback para Google Vertex; por defecto `gemini-3.1-flash-lite-preview`                                                      |
| `TRANSCRIPTION_GEMINI_MODEL`    | _(opcional)_ Modelo usado por transcription worker y legacy transcription Cloud Function; si no existe, se usa `gemini-2.5-flash`               |
| `VERTEX_AI_LOCATION`            | `global` para Gemini; para Claude en Vertex usar una región compatible. No confundir con `CLOUD_TASKS_REGION`, que sigue siendo la región de la cola |

El secret `GCP_SA_KEY` puede eliminarse una vez confirmado que WIF funciona.

**`service-account-json` (opcional en Cloud Run):** el backend puede usar **Application Default Credentials** del service account del servicio (`backend-runner`), que ya tiene acceso a GCS. Si el secreto está vacío o no tiene versión, `get_storage_client()` usa ADC. En local, con `config.settings.develop`, la ruta recomendada es **ADC + impersonación** mediante `GCP_STORAGE_IMPERSONATED_SERVICE_ACCOUNT`; `GCP_STORAGE_SERVICE_ACCOUNT_KEY_PATH` queda como fallback solo si existe una excepción aprobada para usar JSON keys.

### Checklist: que los workflows no fallen

| Requisito                                                                                                                                           | Workflows afectados                               |
| --------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| Variables `GCP_PROJECT_ID`, `WIF_PROVIDER`, `GH_DEPLOYER_SA` definidas y WIF creado en GCP                                                          | Backend, Copilot Agent, Workers, Frontend |
| `BACKEND_SERVICE_ACCOUNT`, `GCS_BUCKET_NAME`, `VITE_API_URL`                                                                                        | Backend deploy                                    |
| `FASTAPI_CORS_ALLOWED_ORIGINS`                                                                                                                       | Backend deploy / admin bootstrap job              |
| `COPILOT_AGENT_SERVICE_ACCOUNT`, `COPILOT_AGENT_DB_NAME`, `VITE_API_URL`                                                                            | Copilot Agent deploy                              |
| `FRONTEND_BUCKET_NAME`, `FRONTEND_SERVICE_ACCOUNT`                                                                                                   | Frontend deploy                                   |
| `TRANSCRIPTION_WORKER_SERVICE_ACCOUNT`, `TRANSCRIPTION_WORKER_URL`                                                                                   | Transcription worker / backend deploy             |
| `DOCUMENT_GENERATION_WORKER_SERVICE_ACCOUNT`, `DOCUMENT_GENERATION_WORKER_URL`                                                                       | Document generation worker / backend deploy       |
| `LANDING_BUCKET_NAME`                                                                                                                               | Landing page deploy                               |
| SA `github-actions-deployer` con los roles del módulo Terraform (p. ej. `run.admin`, `artifactregistry.writer`, `storage.objectAdmin` sobre los buckets usados) | Todos los despliegues                             |

## Problemas frecuentes

| Síntoma                                                                                 | Qué revisar                                                                                                                                                                                                                                   |
| --------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Failed to generate Google Cloud access token` en Actions                               | Variables `WIF_PROVIDER` y `GH_DEPLOYER_SA`; en GCP, que el pool/provider existan y el binding `workloadIdentityUser` apunte al repo correcto (`terraform.tfvars` → `github_repo`).                                                           |
| Backend no conecta a Cloud SQL                                                          | Revisar VPC privada, sidecar `cloud-sql-proxy`, `DB_HOST=127.0.0.1`, `DB_USER=backend-runner@<project>.iam` y que el usuario IAM exista en Cloud SQL.                                                                                         |
| `password authentication failed for user "…"`                                           | En `stg` no debería usarse password. Verifica que el sidecar use `--auto-iam-authn`, que `backend-runner` tenga `roles/cloudsql.instanceUser` y que el usuario IAM exista en la instancia.                                                    |
| `terraform apply` bloqueado por state lock                                              | Otro `plan`/`apply` colgado o Ctrl+C; `terraform force-unlock <id>` tras confirmar que no hay otro proceso usando el state.                                                                                                                   |
| Assets del SPA en `storage.googleapis.com/assets/...` 404                               | `Vite` con `base: '/'` rompe en bucket; el workflow define `VITE_BASE_URL` desde `FRONTEND_BUCKET_NAME` y el router usa `basename`.                                                                                                           |
| Variables de GitHub vacías en Actions                                                   | Las variables solo en el environment `stg` no se ven en `env` a nivel workflow; los jobs de deploy deben tener `environment: stg` (ya aplicado en los workflows).                                                                             |
| `403` al crear bucket / APIs                                                            | Facturación del proyecto activa; APIs habilitadas (`terraform` o bootstrap).                                                                                                                                                                  |
| Cloud Run falla con `Image ... not found`                                               | Usar una imagen bootstrap publica en `cloud_run_image` para el primer `apply`, o publicar primero `fastapi-backend:latest` en Artifact Registry.                                                                                              |
| Cloud Run falla porque `Secret ... versions/latest was not found`                       | En bootstrap, usar `cloud_run_use_secret_manager = false`; después de cargar versiones en Secret Manager, volver a `true` para que el backend lea secretos reales.                                                                            |
| Cloud Run falla al aplicar IAM con `allUsers ... do not belong to a permitted customer` | La organizacion bloquea acceso publico; poner `cloud_run_allow_unauthenticated = false` y exponer el servicio luego mediante una estrategia compatible con tu tenant.                                                                         |
| Bucket frontend falla con `allUsers ... do not belong to a permitted customer`          | La organizacion bloquea buckets publicos; poner `frontend_public_read_enabled = false` y definir luego hosting/CDN alternativo si necesitas SPA publica.                                                                                      |

## Fuera de este documento (aún no en IaC)

- Para reducir costo en `stg`, el repo puede mapear subdominios separados directamente a Cloud Run, por ejemplo `app-stg.notiahealth.com` para la SPA y `api-stg.notiahealth.com` para FastAPI.
- Este path usa `Cloud Run domain mapping`, que según la doc oficial sigue en `Preview` y no se recomienda como ruta principal de producción.
- Cloud Armor queda como endurecimiento posterior.

## Cómo agregar el entorno de producción

1. Crear nuevo proyecto GCP
2. Ejecutar bootstrap (`infra/bootstrap/README.md`) apuntando al proyecto nuevo
3. Copiar `infra/environments/stg/` a `infra/environments/prod/`
4. Editar `backend.tf` (bucket de estado) y `terraform.tfvars` (valores de prod)
5. `terraform init && terraform plan && terraform apply`
6. Configurar variables de GitHub para prod (o usar environments de GitHub)

Ver `infra/environments/prod/README.md` para diferencias específicas stg vs prod.
