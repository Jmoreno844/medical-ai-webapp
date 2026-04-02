# Deuda Técnica — Copilot Agent Runtime

## Estado

Aprobada y explícita.

## Contexto

El copiloto ya tiene un boundary real `frontend -> Django broker -> copilot-agent-service`,
y el slice actual ya cubre `proposal + review + safe apply` con persistencia del thread state y streaming brokered.
La deuda importante que sigue abierta ya no es el apply básico, sino endurecer el writer flow con versionado fuerte, audit trail clínico y mejor UX que el debug panel.

## Deudas activas

### 1. Shared JWT temporal entre Django y `copilot-agent-service`

- **Impacto:** `local` y `stg` usan un secreto compartido (`COPILOT_SERVICE_SHARED_JWT`) tanto para el broker `Django -> copilot-agent-service` como para las tools internas `copilot_agent -> Django`, en vez de auth service-to-service con OIDC/ID token.
- **Por qué se aceptó:** reduce fricción para cerrar el primer flujo brokered y deja el runtime usable en local sin infraestructura adicional.
- **Owner:** `backend/` + `copilot_agent/` + `infra/`.
- **Trigger para pagarla:** antes de considerar el runtime listo para producción clínica o abrir capacidades de escritura.

### 2. Broker por HTTP directo, sin Cloud Tasks

- **Impacto:** Django llama al agent runtime por HTTP directo para crear runs y leer eventos.
- **Por qué se aceptó:** el flujo actual sigue siendo corto y suficiente para validar contratos, proposal/review y thread state duradero sin meter otra pieza de infraestructura.
- **Owner:** `backend/apps/copilot/`.
- **Trigger para pagarla:** cuando los runs del copiloto empiecen a durar más, requieran retries fuertes o fan-out/fan-in pesado.

### 3. Versionado y audit trail aún pragmáticos en el writer flow

- **Impacto:** el patch ya se aplica al documento canonico, pero el control de conflictos sigue apoyándose en una versión enviada por frontend y aún no existe audit trail clínico fuerte del apply.
- **Por qué se aceptó:** permitió cerrar el loop completo `proposal -> review -> apply` sin abrir todavía una refactorización de versionado fuerte del dominio de documentos.
- **Owner:** `backend/apps/copilot/` + `apps/documents/` + `webapp/`.
- **Trigger para pagarla:** antes de abrir el writer flow fuera del debug panel o tratar el copiloto como feature clínica madura.

### 4. `tenant_id` técnico basado en médico

- **Impacto:** el payload actual usa `tenant_id=doctor:{user_id}` porque el dominio backend aún no tiene tenant explícito.
- **Por qué se aceptó:** evita inventar un modelo multi-tenant inexistente solo para arrancar el copiloto.
- **Owner:** `backend/` + arquitectura de producto.
- **Trigger para pagarla:** si el producto introduce tenants/clinics reales o memory namespace multi-tenant.

## Referencias

- [`../architecture/ai-agent-workspace.md`](../architecture/ai-agent-workspace.md)
- [`../architecture/system-overview.md`](../architecture/system-overview.md)
- [`../../implementation_plan_ai_agent_service.md`](../../implementation_plan_ai_agent_service.md)
