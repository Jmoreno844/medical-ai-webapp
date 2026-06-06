# Cloud SQL Production Hardening

## Impacto actual

El entorno `stg` prioriza costo y velocidad de bootstrap. Eso deja varias
configuraciones de Cloud SQL aceptables para staging, pero débiles para una
salida a producción con datos médicos reales.

El riesgo no es solo técnico. En Colombia, los datos de salud son datos
sensibles y la historia clínica exige medidas de custodia, conservación y
confidencialidad. Esta deuda no sustituye asesoría legal, pero sí deja
explícito el baseline técnico pendiente antes de considerar `prod` listo para
operación clínica real.

## Por qué se aceptó temporalmente

En `stg` estamos optimizando:

- costo bajo
- recreación rápida del entorno
- menor complejidad operativa mientras cerramos la migración FastAPI/Cloud Run

Por eso hoy seguimos con una instancia pequeña y más permisiva que lo deseable
para `prod`.

## Estado actual aceptado en `stg`

Hoy `stg` usa una postura de Cloud SQL orientada a staging:

- `availability_type = "ZONAL"`
- `deletion_protection = false` en momentos de recreación/manual reset
- `point_in_time_recovery_enabled = false` en `db-f1-micro`
- sin política explícita cerrada para retener backups tras borrado
- sin estrategia final de auditoría SQL / `pgAudit`
- modo de conexión permisivo del servicio (`ALLOW_UNENCRYPTED_AND_ENCRYPTED`)
  aunque el flujo nominal usa private IP + Cloud SQL Auth Proxy + IAM DB auth

Esto es aceptable para `stg`, no como baseline final de `prod`.

## Boundary responsable

- `infra/modules/cloud_sql/`
- `infra/environments/prod/`
- operación de plataforma / seguridad

## Trigger para pagarla

Antes de:

- almacenar datos médicos reales en `prod`
- habilitar operación clínica real sobre la plataforma
- presentar la arquitectura como baseline productivo de seguridad/compliance

## Cambios esperados para `prod`

### 1. Alta disponibilidad regional

- Cambiar Cloud SQL de `ZONAL` a `REGIONAL`.
- Evaluar el impacto de costo antes de congelar el sizing final.

### 2. Point-in-time recovery

- Habilitar PITR para recuperación ante borrado accidental, corrupción lógica o
  migraciones defectuosas.
- Definir la ventana de recuperación y el costo aceptado.

### 3. Protección contra borrado accidental

- Activar `deletion_protection` en `prod`.
- Definir si los backups deben conservarse tras borrar la instancia.

### 4. Auditoría y evidencia operativa

- Confirmar el baseline mínimo de auditoría:
  - Cloud Audit Logs administrativos
  - evaluar `pgAudit` si se requiere evidencia más fina a nivel SQL
- Definir retención y acceso mínimo necesario a esos logs.

### 5. Endurecimiento de conexiones

- Revisar si `prod` debe seguir permitiendo
  `ALLOW_UNENCRYPTED_AND_ENCRYPTED`.
- Si todo acceso productivo va por proxy/connectors/private IP, endurecer esa
  postura.

### 6. Política para cuentas locales

- Mantener IAM DB auth como vía principal para workloads.
- Si existe algún usuario local tipo break-glass, definir password policy,
  rotación y custodia.

## Módulos / docs afectados

- `infra/modules/cloud_sql/main.tf`
- `infra/modules/cloud_sql/variables.tf`
- `infra/environments/prod/terraform.tfvars`
- `docs/architecture/gcp-infrastructure.md`
