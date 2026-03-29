# Documentación técnica — Django backend

Índice de documentación del proyecto. La documentación de producto vive en esta carpeta;
las **instrucciones orientadas al asistente de IA** están en [`ai-instructions/`](ai-instructions/).

---

## Documentación técnica (raíz de `documentation/`)

| Documento | Propósito | Audiencia |
|-----------|-----------|-----------|
| [`system_map.md`](system_map.md) | Mapa de servicios, inventario completo de endpoints con método/path/auth, variables de entorno, estado en memoria. | Desarrolladores nuevos, revisiones de seguridad. |
| [`flows.md`](flows.md) | Diagramas de secuencia Mermaid para transcripción, generación de documentos y autenticación. | Cualquiera que quiera entender cómo fluye una operación concreta. |
| [`database.md`](database.md) | ERD, tablas reales con campos/tipos/restricciones, índices, migraciones, convenciones de naming. | Backend, DBA, revisiones de modelo. |
| [`backend.md`](backend.md) | Normas de calidad, arquitectura objetivo, seguridad, HIPAA, testing, rendimiento. Checklist normativo. | Code review, onboarding, asistentes de IA. |
| [`jwt_and_auth_contracts.md`](jwt_and_auth_contracts.md) | Contratos de JWT (sesión, usuario, callbacks CF, SSE) y variables relacionadas. | Backend e integración con Cloud Functions. |
| [`secrets_and_environments.md`](secrets_and_environments.md) | Política de secretos por entorno (`DJANGO_SECRET_KEY`, `JWT_SECRET_KEY`, GCP) y módulos de settings explícitos. | Despliegue, seguridad, onboarding. |
| [`docker.md`](docker.md) | Rol de `Dockerfile`, `Dockerfile.test`, Compose y scripts bajo `scripts/docker/`. | Dev local y CI. |
| [`english_rename_map.md`](english_rename_map.md) | Tablas de correspondencia español/mixto → identificadores técnicos en inglés (apps, modelos, rutas, JWT). Texto explicativo en español. | Refactors y revisiones de contrato. |

---

## Instrucciones para IA — [`ai-instructions/`](ai-instructions/)

| Documento | Propósito |
|-----------|-----------|
| [`ai-instructions/general_rules.md`](ai-instructions/general_rules.md) | Convenciones Python, Git (Conventional Commits), seguridad de dependencias. |
| [`ai-instructions/personal_preferences.md`](ai-instructions/personal_preferences.md) | Preferencias del asistente de IA: estilo de código, escalado en Cloud Run. |

---

## Relaciones entre documentos técnicos

```
system_map.md  ──────────────────────────────────────────────────────┐
  (qué existe, dónde está, cómo se conecta)                          │
         │                                                            │
         ▼                                                            ▼
   flows.md                                                    database.md
   (cómo fluye cada operación)                          (qué datos maneja)
         │                                                            │
         └────────────────────┬───────────────────────────────────────┘
                              ▼
                         backend.md
                  (cómo debería hacerse)
```

---

## Cómo navegar si eres nuevo en el proyecto

1. Empieza por `system_map.md` para entender qué servicios existen.
2. Lee `flows.md` para entender cómo funciona la transcripción y la autenticación.
3. Consulta `database.md` para entender el modelo de datos.
4. Lee `backend.md` para conocer los estándares que el equipo quiere alcanzar.
5. Si trabajas con un asistente de IA, enlaza también `ai-instructions/general_rules.md` y `ai-instructions/personal_preferences.md`.
