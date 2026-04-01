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
    cloud_run/          Backend Django
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
   - En `stg`, Terraform crea la VPC privada, Cloud SQL con IP privada + IAM DB auth, el bucket fuente para Cloud Functions y las alertas básicas.
   - En `stg`, `cloud_run_image` arranca con una imagen publica de bootstrap para permitir el primer `apply`; el workflow de backend la reemplaza luego por la imagen real.
   - En `stg`, `cloud_run_use_secret_manager = false` evita que el primer `apply` falle mientras los secrets existen pero todavía no tienen versiones; vuelve a `true` cuando cargues esas versiones.
   - En `stg`, `cloud_run_allow_unauthenticated = false` evita fallos si la organizacion bloquea `allUsers`; luego defines otra estrategia de acceso publico si la necesitas.
   - Si tu organizacion bloquea `allUsers`, deja `frontend_public_read_enabled = false` y no esperes un bucket web publico hasta definir otra estrategia de hosting/CDN.
3. **Secret Manager**: cargar versiones de `django-secret-key` y `jwt-secret-key` (y opcionalmente `service-account-json`).
4. **GitHub**: variables del environment **`stg`** (o del repo) según `docs/architecture/gcp-infrastructure.md`. Los workflows de deploy usan `environment: stg`. Sin `WIF_PROVIDER` / `GH_DEPLOYER_SA` los workflows no autentican.
5. **CI**:
   - Ejecutar primero el workflow de Cloud Functions para que existan `transcription-endpoint` y `document-workflow`.
   - Luego ejecutar backend / frontend, o dejar que corran por `push` / `workflow_dispatch`.

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

Los outputs incluyen URL de Cloud Run, Cloud SQL private IP, buckets, service accounts y el WIF provider path necesario para configurar GitHub.

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
echo -n "tu-valor" | gcloud secrets versions add django-secret-key --data-file=- --project=vext-stg
```

Repetir para cada secret necesario: `jwt-secret-key`. `service-account-json` es **opcional** en Cloud Run si el contenedor usa solo ADC del SA `backend-runner` para GCS (comportamiento por defecto del código); en local desarrollo la ruta recomendada es ADC + impersonación (`GCP_STORAGE_IMPERSONATED_SERVICE_ACCOUNT`) con `config.settings.develop`.

## Configurar GitHub después de terraform apply

Después del primer apply exitoso, copiar los outputs de Terraform a las variables del environment **`stg`** (Settings → Environments → stg) o a **repository variables** si no usas environments:

- `GCP_PROJECT_ID`
- `WIF_PROVIDER` (output `workload_identity_provider`)
- `GH_DEPLOYER_SA` (output `github_actions_deployer_email`)
- `BACKEND_SERVICE_ACCOUNT` (output `backend_service_account`)
- `GCS_BUCKET_NAME` (output `audio_bucket`)
- `FRONTEND_BUCKET_NAME` (output `frontend_bucket`)
- `CF_SOURCE_BUCKET` (output `cf_source_bucket`)
- `VITE_API_URL` (output `cloud_run_url`)
- `LANDING_BUCKET_NAME` si el workflow de landing page usa un bucket distinto
- *(opcional)* `CF_SOURCE_OBJECT` — ver `docs/architecture/gcp-infrastructure.md`

Luego se puede eliminar el secret `GCP_SA_KEY` de GitHub.

## Terraform y GitHub Actions (matiz)

- **Cloud Run**: el módulo fija una imagen inicial y la topología base del servicio (VPC egress + sidecar del Cloud SQL Auth Proxy). El workflow de backend sustituye la imagen y actualiza env vars del backend.
- **Cloud Functions**: en `stg`, Terraform **no** crea las funciones. Terraform solo crea el bucket fuente y las cuentas/roles necesarios; el workflow **sube el zip** y hace **`gcloud functions deploy`**.

## Documentación relacionada

- `bootstrap/README.md` — comandos `gcloud` para el bootstrap inicial
- `docs/architecture/gcp-infrastructure.md` — matriz IAM, secrets, lifecycle, naming
- `docs/decisions/0002-notificaciones-en-tiempo-real-sse-en-memoria.md` — por qué `max-instances=1`
