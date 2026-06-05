# Infraestructura (Terraform)

Gestiona todos los recursos GCP de VextHealth. Cada entorno (`stg`, `prod`) tiene su propio directorio con `terraform.tfvars` y backend de estado separado.

## Estructura

```
infra/
  bootstrap/          # Pasos manuales (una sola vez por proyecto GCP)
  modules/            # Módulos reutilizables
    project_services/   APIs de GCP
    network/            VPC + private service access
    service_accounts/   SAs + IAM bindings
    secret_manager/     Shells de secrets (sin valores)
    artifact_registry/  Repositorio Docker
    cloud_sql/          PostgreSQL
    storage_buckets/    Audio + frontend SPA
    cloud_run/          Cloud Run services (backend + frontend + copilot agent + workers)
    cloud_tasks/        Cola de transcripción
    workload_identity/  WIF para GitHub Actions
    monitoring/         Alertas básicas + budget
  environments/
    stg/                vext-stg
    prod/               (placeholder)
```

## Requisitos previos

- Proyecto GCP con **facturación activa** (GCS, Cloud SQL, etc.)
- [Terraform >= 1.5](https://developer.hashicorp.com/terraform/install)
- `gcloud` CLI autenticado (usuario con rol **Owner** o equivalente para el primer bootstrap)
- Haber completado el bootstrap (`bootstrap/README.md`)

## Primera vez (orden recomendado)

1. **Bootstrap** (`bootstrap/README.md`): bucket de estado + SA `terraform-admin` + IAM.
2. **Terraform** (como tu usuario o con clave temporal de `terraform-admin`):
   - `cd environments/stg && terraform init && terraform plan`.
   - En `stg`, Terraform crea la VPC privada, Cloud SQL con IP privada + IAM DB auth, workers Cloud Run, colas Cloud Tasks, el bucket fuente para Cloud Functions legacy y las alertas básicas.
   - En `stg`, `cloud_run_image` arranca con una imagen publica de bootstrap para permitir el primer `apply`; el workflow de backend la reemplaza luego por la imagen real.
   - En `stg`, `cloud_run_use_secret_manager = false` evita que el primer `apply` falle mientras los secrets existen pero todavía no tienen versiones; vuelve a `true` cuando cargues esas versiones.
   - En `stg`, `cloud_run_allow_unauthenticated = false` evita fallos si la organizacion bloquea `allUsers`; luego defines otra estrategia de acceso publico si la necesitas.
   - Si tu organizacion bloquea `allUsers`, deja `frontend_public_read_enabled = false` y no esperes un bucket web publico hasta definir otra estrategia de hosting/CDN.
3. **Secret Manager**: cargar versiones de `jwt-secret-key`, `copilot-service-shared-jwt`, `audit-ip-hmac-secret`, `audit-ip-encryption-key` y un placeholder inicial de `admin-bootstrap-password` (y opcionalmente `service-account-json`).
4. **GitHub**: variables del environment **`stg`** (o del repo) según `docs/architecture/gcp-infrastructure.md`. Los workflows de deploy usan `environment: stg`. Sin `WIF_PROVIDER` / `GH_DEPLOYER_SA` los workflows no autentican.
5. **CI**:
   - Ejecutar primero los workflows de `transcription_worker` y `document_generation_worker` para que existan las URLs privadas.
   - Luego ejecutar backend / frontend, o dejar que corran por `push` / `workflow_dispatch`.
   - El workflow de frontend despliega `vexthealth-frontend` en Cloud Run; para `stg` barato, la SPA y el API pueden exponerse con subdominios separados usando `Cloud Run domain mapping`.

**Autenticación local de Terraform:** con usuario humano basta `gcloud auth application-default login` en muchos casos; si usas la SA `terraform-admin`, exporta `GOOGLE_APPLICATION_CREDENTIALS` a la clave JSON (solo transitoria; revócala tras validar WIF).

## Flujo de trabajo

### 1. Bootstrap (una sola vez por proyecto)

```bash
cd infra/bootstrap
# Seguir instrucciones de README.md
```

### 2. Inicializar

```bash
cd infra/environments/stg
terraform init
```

### 3. Plan

```bash
terraform plan
```

Siempre revisar el plan antes de aplicar. Buscar destrucción accidental de recursos.

### 4. Aplicar

```bash
terraform apply
```

### 5. Obtener outputs

```bash
terraform output
```

Los outputs incluyen URL de Cloud Run, URL del copilot agent, Cloud SQL private IP, buckets, service accounts y el WIF provider path necesario para configurar GitHub.

## Variables sensibles

El backend `stg` ya no depende de `db_password` ni `db_user` en Terraform; la conexión usa Cloud SQL IAM DB auth mediante `backend-runner`.

El `terraform state` sigue siendo sensible y debe mantenerse en un bucket GCS privado con versionado habilitado.

## Agregar un entorno nuevo (e.g. prod)

1. Crear proyecto GCP y ejecutar el bootstrap
2. Copiar `environments/stg/` a `environments/prod/`
3. Editar `backend.tf` con el bucket de estado del nuevo proyecto
4. Editar `terraform.tfvars` con los valores del nuevo proyecto
5. `terraform init && terraform plan && terraform apply`

Ver `environments/prod/README.md` para diferencias específicas.

## Cargar secrets manualmente

Terraform solo crea los recursos de Secret Manager vacíos. Para cargar valores:

```bash
echo -n "tu-valor" | gcloud secrets versions add jwt-secret-key --data-file=- --project=vext-stg
```

Repetir para cada secret necesario:

- `jwt-secret-key`
- `copilot-service-shared-jwt`
- `audit-ip-hmac-secret`
- `audit-ip-encryption-key`
- `admin-bootstrap-password` (deja un placeholder inicial para que el Cloud Run Job pueda desplegar; luego rótalo antes de crear/resetear admins)

`service-account-json` es **opcional** en Cloud Run si el contenedor usa solo ADC del SA `backend-runner` para GCS (comportamiento por defecto del código); en local desarrollo la ruta recomendada es ADC + impersonación (`GCP_STORAGE_IMPERSONATED_SERVICE_ACCOUNT`) con `config.settings.develop`.

## Configurar GitHub después de terraform apply

Después del primer apply exitoso, copiar los outputs de Terraform a las variables del environment **`stg`** (Settings → Environments → stg) o a **repository variables** si no usas environments:

- `GCP_PROJECT_ID`
- `WIF_PROVIDER` (output `workload_identity_provider`)
- `GH_DEPLOYER_SA` (output `github_actions_deployer_email`)
- `BACKEND_SERVICE_ACCOUNT` (output `backend_service_account`)
- `FRONTEND_SERVICE_ACCOUNT` (output `frontend_service_account`)
- `COPILOT_AGENT_SERVICE_ACCOUNT` (output `copilot_agent_service_account`)
- `TRANSCRIPTION_WORKER_SERVICE_ACCOUNT` (output `transcription_worker_service_account`)
- `COPILOT_AGENT_DB_NAME` (valor de `terraform.tfvars`)
- `GCS_BUCKET_NAME` (output `audio_bucket`)
- `FRONTEND_BUCKET_NAME` (output `frontend_bucket`)
- `CF_SOURCE_BUCKET` (output `cf_source_bucket`)
- `VITE_API_URL` (output `cloud_run_url`)
- `FRONTEND_DOMAIN_NAME` y `BACKEND_DOMAIN_NAME` si quieres documentarlos en tu inventario de entorno
- `COPILOT_AGENT_URL` (output `copilot_agent_cloud_run_url`)
- `LANDING_BUCKET_NAME` si el workflow de landing page usa un bucket distinto
- *(opcional)* `CF_SOURCE_OBJECT` — ver `docs/architecture/gcp-infrastructure.md`

Luego se puede eliminar el secret `GCP_SA_KEY` de GitHub.

## Terraform y GitHub Actions (matiz)

- **Cloud Run**: el módulo fija una imagen inicial y la topología base de backend,
  frontend, copilot, transcription worker y document generation worker. Los workflows sustituyen las imágenes y
  actualizan env vars por servicio.
- **Cloud Functions**: en `stg`, Terraform **no** crea las funciones legacy. Terraform solo crea el bucket fuente y las cuentas/roles necesarios; el workflow **sube el zip** y despliega `transcription-endpoint`.

## Documentación relacionada

- `bootstrap/README.md` — comandos `gcloud` para el bootstrap inicial
- `docs/architecture/gcp-infrastructure.md` — matriz IAM, secrets, lifecycle, naming
- `docs/decisions/0002-notificaciones-en-tiempo-real-sse-en-memoria.md` — por qué `max-instances=1`
