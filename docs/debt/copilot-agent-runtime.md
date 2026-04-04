# Deuda Técnica — Copilot Agent Runtime

## Estado

Aprobada y explícita.

## Contexto

El copiloto ya tiene un boundary real `frontend -> Django broker -> copilot-agent-service`,
y el slice actual ya cubre `proposal + review + safe apply` con persistencia del thread state y streaming brokered.
La deuda importante que sigue abierta ya no es el apply básico, sino endurecer el writer flow con versionado fuerte, audit trail clínico y mejor UX que el debug panel.
En el sidechat actual, `thread_id` ya identifica una conversación real: Django crea uno nuevo al iniciar chat, el frontend lo mantiene solo en memoria del panel y LangGraph lo usa como checkpoint key para conservar contexto entre mensajes del mismo chat.

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

### 2.5. Reintentos/availability del planner LLM aún minimalistas

- **Impacto:** el runtime ya no usa fallback heurístico para routing ni drafting; el planner/drafter hacen un retry técnico corto y, si Vertex sigue fallando o devuelve salida inválida, el run cierra en `failed`.
- **Por qué se aceptó:** evita degradaciones silenciosas y mantiene el comportamiento clínico acotado mientras se estabiliza el contrato estructurado del planner/tool loop nativo.
- **Owner:** `copilot_agent/`.
- **Trigger para pagarla:** cuando se quiera endurecer disponibilidad con retries explícitos, circuit breakers o modelos secundarios sin reintroducir heurísticas de producto.

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

### 5. Explicit context caching diferido para un futuro QA helper

- **Impacto:** el runtime actual del `document helper` no persiste ni reutiliza `cached_content` explícito de Vertex entre chats/superficies. Se apoya en continuidad del hilo y `implicit caching` del proveedor.
- **Por qué se aceptó:** en el slice actual, el médico normalmente usa una sola conversación continua para editar o consultar sobre el documento del encounter; ahí conviene priorizar payloads append-only, orden determinista del contexto y continuidad del chat antes de sumar lifecycle de caches explícitos con PHI.
- **Casos donde sí podría valer la pena luego:** reuso del mismo pack de PDFs/historia en una nueva superficie de chat, conversaciones muy largas que requieran summarization/reinicio, o consultas pausadas y retomadas horas después con el mismo contexto pesado.
- **Regla de producto para el futuro:** si se introduce, el `explicit caching` debe aplicarse a un `stable context pack` (PDFs, historia longitudinal, labs previos, documentos históricos seleccionados), no a la transcripción realtime que sigue llegando por chunks.
- **Owner:** `copilot_agent/` + `backend/apps/copilot/` + diseño de producto del QA helper.
- **Trigger para pagarla:** cuando exista un QA helper longitudinal o multi-superficie que reutilice contexto pesado fuera del mismo hilo conversacional.

### 6. Heurística fina para lectura global del documento aún pragmática

- **Impacto:** el runtime ya expone `read_document(mode="full")` para casos como inserts al inicio/final o cambios amplios, pero todavía no tiene una optimización más fina para leer solo la región terminal/inicial cuando eso bastaría.
- **Por qué se aceptó:** destraba ya mismo los casos clínicos donde un span inicial no alcanza y mantiene simple la surface del agente mientras se estabiliza la estrategia de anchors por contenido.
- **Owner:** `copilot_agent/` + `backend/apps/copilot/`.
- **Trigger para pagarla:** cuando el costo de `mode="full"` en notas largas empiece a notarse o aparezcan suficientes casos de edición donde leer solo el final del documento sea claramente mejor.

## Referencias

- [`../architecture/ai-agent-workspace.md`](../architecture/ai-agent-workspace.md)
- [`../architecture/system-overview.md`](../architecture/system-overview.md)
- [`../../implementation_plan_ai_agent_service.md`](../../implementation_plan_ai_agent_service.md)
- [`../decisions/0006-explicit-context-caching-futuro-qa-helper.md`](../decisions/0006-explicit-context-caching-futuro-qa-helper.md)
- [`../decisions/0007-writer-flow-anchors-y-lectura-completa.md`](../decisions/0007-writer-flow-anchors-y-lectura-completa.md)
