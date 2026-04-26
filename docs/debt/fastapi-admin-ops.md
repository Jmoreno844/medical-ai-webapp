# Django admin, Silk, y backoffice sin SPA

**Estado:** deuda aceptada. No bloquea quitar `backend/` del runtime de la
aplicación clínica (SPA + FastAPI + cloud functions) una vez el schema, tests y
operación estén alineados con [backend-fastapi-migration](../architecture/backend-fastapi-migration.md).

## Qué da hoy el monolito (cuando se despliega)

- **Django admin:** UI para inspeccionar modelos (`django.contrib.admin`),
  con logging en `django_admin_log` (tabla que **no** entra en el baseline
  Alembic; solo instalaciones aún servidas con Django + migraciones
  canónicas).
- **Django Silk:** trazas y perfiles de requests, tablas bajo el prefijo `silk_`
  (tampoco en el baseline FastAPI; útiles en stg/legacy de depuración).

Ninguna de esas piezas se usa en el recorrido del doctor en el webapp. La
configuración actual monta admin/Silk vía `INSTALLED_APPS` y
`config/urls.py` (solo mientras exista el monolito en ese entorno).

## Quién podría necesitarlas aún

- Operadores o desarrolladores que inspeccionan filas a mano en un incidente
  sin pasar por SQL/Cloud Console.
- Prototipos de acceso a datos o auditoría mientras no haya otra consola
  aprobada.

## Workarounds mientras dure la deuda

- Conectar con cliente SQL/Cloud SQL a la instancia, con mínima superficie
  (IAM, solo operadores, sin almacenar credenciales en repositorio).
- Export o queries de solo metadatos (nunca registro de texto clínico
  en logs o tickets sin política de PHI).

## Opciones de reemplazo (futuro)

- Consola mínima **dentro** de `backend_fastapi` (rutas staff-only, con los
  mismos controles de auth/roles que el resto del producto) para listados
  read-only o acciones puntuales.
- Herramienta externa de gobierno (SIEM, audit DB) conectada al mismo
  Cloud SQL, fuera de este repo.
- Añadir tablas admin/Silk a un *branch* de migración aparte, **no** al
  baseline mínimo en verde, si en algún despliegue aún hace falta 1:1 con el
  monolito.

No duplicar esta deuda en cada archivo; al cambiar el plan de reemplazo,
actualizar **solo** este documento y un puntero en
`docs/architecture/backend-fastapi-migration.md`.
