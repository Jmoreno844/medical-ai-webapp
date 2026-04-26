# Deuda Técnica Canónica

Esta carpeta existe para deudas **aceptadas y transversales**, no para TODOs de bajo nivel.

Usa `docs/debt/` cuando la deuda:

- afecta más de un módulo o servicio
- cambia decisiones de seguridad, arquitectura u operación
- necesita quedar visible para futuros chats/agentes
- tiene un trigger claro para pagarse

Cada deuda debe dejar claro:

- impacto actual
- por qué se aceptó temporalmente
- owner o boundary responsable
- trigger o condición para pagarla
- links a la arquitectura o módulos afectados

Regla de duplicación:

- aquí vive la explicación canónica
- en `AGENTS.md`, docs de arquitectura o módulos sensibles deja solo una nota breve con link
- evita copiar el mismo texto completo en varios lados

Deudas actuales:

- [`observability-baseline.md`](observability-baseline.md) — baseline minimo de alertas, dashboards y runbooks antes de launch.
- [`copilot-agent-runtime.md`](copilot-agent-runtime.md) — deuda temporal del runtime y auth interna del copiloto.

