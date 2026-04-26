# Visión General del Sistema

Este documento describe la arquitectura global de la plataforma, sus componentes principales y cómo interactúan entre sí.

## 1. Arquitectura de Alto Nivel

El sistema es una plataforma fullstack con un **API FastAPI** en `backend_fastapi/`,
funciones serverless en GCP, un runtime del copiloto y una SPA en React.

```mermaid
graph LR
    subgraph client ["Cliente"]
        Browser["React + Vite\n(SPA)"]
    end

    subgraph gcp ["Google Cloud Platform"]
        subgraph backend_run ["Cloud Run"]
            Backend["FastAPI API"]
            Copilot["copilot-agent-service\n(LangGraph)"]
        end
        subgraph functions ["Cloud Functions"]
            CF_Trans["transcription-endpoint"]
            CF_Gen["document-workflow"]
        end
        GCS["Cloud Storage\n(audio clínico)"]
        Vertex["Vertex AI · Gemini"]
        PG["Cloud SQL · PostgreSQL"]
        SM["Secret Manager"]
    end

    Browser -->|"REST + cookies JWT"| Backend
    Browser -->|"PUT audio directo"| GCS
    Browser -->|"SSE stream"| Backend

    Backend -->|"SQLAlchemy async"| PG
    Backend -->|"signed URL"| GCS
    Backend -->|"JWT + payload"| CF_Trans
    Backend -->|"JWT + payload"| CF_Gen
    Backend -->|"internal broker contract"| Copilot
    Backend -->|"secrets"| SM

    Copilot -->|"checkpoints + memory"| PG
    Copilot -->|"Gemini / tools orchestration"| Vertex

    CF_Trans -->|"gs:// URI"| GCS
    CF_Trans -->|"Gemini API"| Vertex
    CF_Trans -->|"PATCH Bearer JWT"| Backend

    CF_Gen -->|"Gemini streaming"| Vertex
    CF_Gen -->|"chunks Bearer JWT"| Backend
```

---

## 2. Flujo de Transcripción de Audio

El camino completo desde que el médico detiene la grabación hasta que el texto aparece en el editor. En el slice migrado, el kickoff y los callbacks de este flujo viven en FastAPI bajo `/api/v1`.

```mermaid
sequenceDiagram
    actor Medico
    participant Browser as React (Browser)
    participant Backend as API Backend
    participant GCS as Cloud Storage
    participant CF as CF transcription-endpoint
    participant Gemini as Vertex AI · Gemini

    rect rgb(240, 248, 255)
        note over Browser,GCS: Paso 1 — Subida de audio
        Medico->>Browser: Detiene grabación
        Browser->>Backend: POST /encounters/:id/audio/upload-url
        Backend-->>Browser: { upload_url, filename }
        Browser->>GCS: PUT audio (directo, signed URL)
    end

    rect rgb(255, 248, 240)
        note over Browser,CF: Paso 2 — Inicio de transcripción
        Browser->>Backend: POST /api/v1/transcription/start
        Backend->>Backend: Genera JWT callback FastAPI (15 min)
        Backend->>Backend: Encola Cloud Task
        Backend-->>Browser: 200 OK { queued: true }
        Backend->>CF: POST { audio_uri, auth_token } via Cloud Tasks
    end

    rect rgb(240, 255, 248)
        note over CF,Gemini: Paso 3 — Procesamiento con IA
        CF->>GCS: Lee audio (gs:// URI)
        CF->>Gemini: generate_content(audio + prompt)
        Gemini-->>CF: Texto transcrito
    end

    rect rgb(248, 240, 255)
        note over CF,Browser: Paso 4 — Actualización y notificación
        CF->>Backend: PATCH /api/v1/documents/by-function/:id { content }
        Backend->>Backend: Guarda en PostgreSQL
        Backend-->>Browser: SSE evento "transcription_complete"
        CF->>Backend: POST /api/v1/transcription/notify-complete
        Backend->>Backend: Marca encuentro como transcrito
        CF-->>Backend: 200 OK
        Backend-->>Browser: 200 OK
    end
```

---

## 3. Flujo de Generación de Documentos

Genera un documento clínico (SOAP, nota de evolución, etc.) combinando la transcripción, el contexto del paciente y una plantilla, con streaming en tiempo real vía SSE. En el slice migrado, el kickoff, SSE token y callbacks de generación viven en FastAPI bajo `/api/v1`.

```mermaid
sequenceDiagram
    actor Medico
    participant Browser as React (Browser)
    participant Backend as API Backend
    participant CF as CF document-workflow
    participant Gemini as Vertex AI · Gemini

    rect rgb(240, 248, 255)
        note over Browser,Backend: Paso 1 — Apertura de canal SSE
        Browser->>Backend: POST /api/v1/documents/:doc_id/sse-token
        Backend-->>Browser: { token } (5 min)
        Browser->>Backend: GET /api/v1/sse/documents/:id/:token
        note right of Browser: Conexión SSE abierta (streaming)
    end

    rect rgb(255, 248, 240)
        note over Browser,CF: Paso 2 — Trigger de generación
        Medico->>Browser: Clic en "Generar Documento"
        Browser->>Backend: POST /api/v1/documents/generate
        Backend->>Backend: Valida permisos y genera JWT callback (30 min)
        Backend->>CF: POST validate_only=true (síncrono)
        CF-->>Backend: 200 OK
        Backend-->>Browser: 200 OK { process_id }
        note right of Backend: Lanza hilo background →
    end

    rect rgb(240, 255, 248)
        note over Backend,Gemini: Paso 3 — Generación con streaming
        Backend->>CF: POST payload completo (background)
        CF->>Gemini: generate_content(prompt, stream=True)

        loop Cada chunk de texto
            Gemini-->>CF: chunk
            CF->>Backend: POST /api/v1/documents/generation-chunk
            Backend-->>Browser: SSE "generation_chunk" { chunk }
        end
    end

    rect rgb(248, 240, 255)
        note over Backend,Browser: Paso 4 — Finalización
        CF->>Backend: POST generation-chunk { is_complete: true }
        Backend->>Backend: Guarda documento completo en BD
        Backend-->>Browser: SSE "generation_complete"
    end
```

---

## 4. Componentes y Responsabilidades

| Componente | Stack | Responsabilidad |
|------------|-------|-----------------|
| **Frontend** `webapp/` | React 18, Vite, TypeScript, Tailwind | SPA del médico. Maneja grabación, UI del editor y conexión SSE. |
| **API principal** `backend_fastapi/` | FastAPI, SQLAlchemy async, PostgreSQL | API bajo `/api/v1`, orquestación, JWTs, hub SSE, callbacks y migraciones Alembic. |
| **Copilot Agent** `copilot_agent/` | Python, FastAPI, LangGraph | Runtime del copiloto; broker hacia el API principal. |
| **CF Transcripción** | Python, Functions Framework | Recibe audio de GCS → llama a Gemini → devuelve texto al API. |
| **CF Generación** | Python, Functions Framework | Recibe contexto+plantilla → streaming desde Gemini → envía chunks al API. |
| **Cloud Storage** | GCS | Almacena los audios clínicos. El frontend sube directo vía signed URL. |
| **Vertex AI · Gemini** | Managed (GCP) | Modelo de IA para transcripción y generación de documentos clínicos. |
| **PostgreSQL** | Cloud SQL | Base de datos principal: encuentros, documentos, pacientes, plantillas. |

---

## 5. Puntos de Atención Arquitectónica

- **Hub SSE en memoria**: el hub en `backend_fastapi` usa memoria de proceso. Con múltiples réplicas en Cloud Run, un evento en la instancia A no llega a clientes en la B. Resolver con Redis o Pub/Sub en el futuro.
- **Backend público + DB privada**: Cloud Run sigue público para la SPA, pero PostgreSQL queda aislado por IP privada y acceso vía Cloud SQL Auth Proxy + IAM DB auth.
- **Agent runtime separado**: LangGraph no vive dentro del backend principal. El backend hace de broker y conserva la autoridad clínica/transaccional.
- **Auth interna temporal del copiloto**: el API (FastAPI) y `copilot-agent-service` usan un `shared JWT` temporal en `local`/`stg`; ver deuda canónica en [`../debt/copilot-agent-runtime.md`](../debt/copilot-agent-runtime.md).
- **Audio no se borra al transcribir**: `audio_expires_at` controla el acceso vía API, pero el blob en GCS solo se elimina si el médico lo solicita explícitamente.
- **Cloud Functions IAM-auth**: las funciones están desplegadas con `--no-allow-unauthenticated`; la seguridad depende de IAM de invocación + JWT de callback. El `JWT_SECRET_KEY` no debe filtrarse.

---

## 6. Observabilidad y trazas

OpenTelemetry enlaza las peticiones **navegador (XHR/axios) → API (FastAPI) → Cloud Functions → callbacks al API** cuando el export está configurado (OTLP/Jaeger en local, Cloud Trace en GCP con `GOOGLE_CLOUD_PROJECT`). Los logs del backend incluyen `trace_id` / `span_id` para correlación. Detalle y variables: [`../backend/tracing.md`](../backend/tracing.md). Limitaciones: SSE (`EventSource` sin cabeceras W3C) y subida directa a GCS con signed URL no continúan el mismo trace de extremo a extremo.
