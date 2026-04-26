# Copilot Agent Instructions

## Scope

Estas instrucciones aplican a `copilot_agent/`.

## Mission

Mantener este servicio como runtime dedicado del copiloto clínico:

- separado del backend principal
- orientado a LangGraph Graph API
- con estado durable fuera de memoria local
- sin convertirse en una segunda fuente de verdad clínica

## Boundaries

- no exponer endpoints públicos al navegador
- no aplicar cambios clínicos sensibles sin review externo
- no tocar directamente la DB clínica operativa para writes finales
- no mover auth de usuarios o lógica de permisos desde FastAPI a este servicio

## Code Rules

- preferir funciones pequeñas y nodos explícitos
- el estado del grafo debe ser fácil de inspeccionar y extender
- los tools deben ser estrechos y auditables
- comentarios solo para intent, guard rails o tradeoffs

## Commenting Policy (enforced)

Este codebase usa AI agents como editores frecuentes. Los comentarios son la única
forma de transmitir contexto que no se puede inferir leyendo el código.

**Cuándo SÍ comentar — obligatorio:**

- Decisiones que descartan una alternativa más obvia (ej. por qué json_schema y no function_calling)
- Invariantes que el agente rompería si no los conoce (ej. RESET_MARKER, AFC disable, thread checkpoint scope)
- Workarounds o stubs temporales con una nota de qué los reemplazaría (ej. `apply_patch` vacío)
- Límites de tamaño o presupuesto con la razón (ej. excerpt:600 en turn context vs 12000 en ToolMessage)
- Cualquier comportamiento del proveedor LLM que sea sorprendente (ej. Gemini empty response, AFC side loop)
- Flujo de ownership inter-servicio cuando no está en el nombre del módulo (ej. FastAPI es quien escribe, no el agente)

**Cuándo NO comentar:**

- Sintaxis obvia (`for`, `if`, `return`)
- Lo que el nombre de la función ya dice
- Explicaciones largas que pertenecen a `docs/` — en esos casos, deja solo una línea con la referencia

**Formato:**

- Comentarios en inglés para constraints de infraestructura/plataforma
- Comentarios en español para lógica clínica o reglas de negocio del dominio médico
- Máximo 4-5 líneas por comentario; si necesita más, el contexto pertenece a `docs/`

## Docs

- setup local y endpoints → `copilot_agent/README.md`
- runtime de implementación (tools, state, workflows, graph) → `docs/agent/RUNTIME.md`
- arquitectura de capas, políticas de seguridad → `docs/architecture/ai-agent-workspace.md`
- decisiones de producto del writer → `docs/notes/copilot-clinical-writer-direction.md`
- deuda técnica → `docs/debt/copilot-agent-runtime.md`
- mantener `docs/agent/RUNTIME.md` al día cuando cambien tools, state, graph, o flujos principales
