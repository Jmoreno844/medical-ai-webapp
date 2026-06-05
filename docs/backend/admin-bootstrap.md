# Bootstrap de Admin en GCP

Este documento define el flujo seguro para crear o promover admins internos en
`stg` y `prod` sin abrir endpoints públicos ni pegar secretos en GitHub.

## Principios

- Se usa un **Cloud Run Job** administrativo, no una VM dedicada.
- Los secretos runtime viven en **Secret Manager**, no en GitHub.
- El password de bootstrap se entrega por `ADMIN_BOOTSTRAP_PASSWORD`, nunca por
  args de CLI en `stg` o `prod`.
- El default operativo es:
  - `role=admin`
  - `is_staff=true`
  - `is_superuser=false`

`is_superuser=true` queda reservado para muy pocas cuentas operativas.

## Secretos requeridos

Terraform crea los shells; los valores/versiones se cargan manualmente.

Requeridos para que el backend y el job funcionen:

- `jwt-secret-key`
- `copilot-service-shared-jwt`
- `audit-ip-hmac-secret`
- `audit-ip-encryption-key`
- `admin-bootstrap-password`

Recomendación para `admin-bootstrap-password`:

- dejar una **versión placeholder** al bootstrap del entorno para que el job se
  pueda desplegar sin fallar por `latest`
- antes de crear o resetear un admin, reemplazarla por una versión temporal con
  el password real
- después de usarla, rotarla otra vez o deshabilitar la versión sensible

Ejemplo para cargar una versión:

```bash
echo -n 'valor-seguro' | gcloud secrets versions add admin-bootstrap-password \
  --data-file=- \
  --project=vext-stg
```

## Prerrequisitos IAM

El operador necesita permisos para:

- ejecutar Cloud Run Jobs
- leer Cloud Logging
- cargar/rotar versiones en Secret Manager

El runtime del job usa `backend-runner@...` y hereda:

- Cloud SQL IAM DB auth
- Secret Manager access
- conectividad privada

## Crear un admin nuevo

1. Cargar una versión temporal en `admin-bootstrap-password`.
2. Ejecutar el job con los args del usuario:

```bash
gcloud run jobs execute vexthealth-backend-admin-bootstrap \
  --region=us-east1 \
  --args=scripts/create_admin.py,--email=admin@tu-dominio.com,--name=Ada,--last-name=Lovelace
```

3. Revisar logs y verificar que el usuario quedó con:
   - `role=admin`
   - `is_staff=true`
   - `is_superuser=false`
4. Rotar o deshabilitar la versión sensible de `admin-bootstrap-password`.

## Promover un usuario existente

Si el usuario ya existe y no vas a resetearle password:

```bash
gcloud run jobs execute vexthealth-backend-admin-bootstrap \
  --region=us-east1 \
  --args=scripts/create_admin.py,--email=doctor@tu-dominio.com,--name=Ada,--last-name=Lovelace
```

En este caso `ADMIN_BOOTSTRAP_PASSWORD` puede quedar con placeholder; el script
no la usa si no está creando usuario nuevo ni se pide `--update-password`.

## Resetear password durante la promoción

1. Cargar una nueva versión temporal en `admin-bootstrap-password`.
2. Ejecutar:

```bash
gcloud run jobs execute vexthealth-backend-admin-bootstrap \
  --region=us-east1 \
  --args=scripts/create_admin.py,--email=doctor@tu-dominio.com,--name=Ada,--last-name=Lovelace,--update-password
```

## Superuser excepcional

Solo si hay una necesidad operativa explícita:

```bash
gcloud run jobs execute vexthealth-backend-admin-bootstrap \
  --region=us-east1 \
  --args=scripts/create_admin.py,--email=root@tu-dominio.com,--name=Ada,--last-name=Lovelace,--superuser
```

## Verificación y logs

Listar ejecuciones:

```bash
gcloud run jobs executions list \
  --job=vexthealth-backend-admin-bootstrap \
  --region=us-east1
```

Leer logs:

```bash
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="vexthealth-backend-admin-bootstrap"' \
  --limit=50 \
  --project=vext-stg
```

Verificar además en auditoría:

- `user.created`
- `user.role_changed`
- `user.activated` cuando aplique

## Relación con GitHub Actions

- GitHub Actions **no** sube valores a Secret Manager.
- GitHub `environment vars` contienen solo config no sensible.
- Los workflows de deploy solo montan secretos ya existentes por referencia.
- El workflow del backend sincroniza la **imagen** del Cloud Run Job para que el
  job use el mismo release que el backend, pero no toca valores secretos.
