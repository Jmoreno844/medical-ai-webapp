# Visión General del Sistema

Este documento describe la arquitectura global de la plataforma, sus componentes principales y cómo interactúan entre sí.

## 1. Arquitectura de Alto Nivel

El sistema es una plataforma fullstack con un **API FastAPI** en `backend_fastapi/`,
workers Cloud Run privados, un runtime del copiloto y una SPA en React.

```mermaid
graph LR
    subgraph client ["Cliente"]
        Browser["React + Vite\n(SPA)"]
    end

    subgraph gcp ["Google Cloud Platform"]
        subgraph backend_run ["Cloud Run"]
            Backend["FastAPI API"]
            Worker["transcription-worker\n(Silero VAD + Gemini STT)"]
            DocWorker["document-generation-worker\n(Gemini streaming)"]
            Copilot["copilot-agent-service\n(LangGraph)"]
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
    Backend -->|"Cloud Tasks OIDC\nIDs only"| DocWorker
    Backend -->|"internal broker contract"| Copilot
    Backend -->|"secrets"| SM

    Copilot -->|"checkpoints + memory"| PG
    Copilot -->|"Gemini / tools orchestration"| Vertex

    Backend -->|"Cloud Tasks OIDC"| Worker
    Worker -->|"read sections"| GCS
    Worker -->|"Silero VAD local\n+ Gemini async"| Vertex
    Worker -->|"OIDC result callbacks"| Backend

    DocWorker -->|"Gemini streaming"| Vertex
    DocWorker -->|"chunks Bearer JWT"| Backend
```

---

## 2. Flujo de Transcripción de Audio

El camino implementado usa transcripción near realtime por secciones. Mientras
el médico graba, el navegador corta audio en secciones temporales, conserva una
cola local en IndexedDB y sube cada blob directo a Cloud Storage mediante signed
URLs. FastAPI registra cada seccion de forma idempotente, Cloud Tasks dispara el
servicio `transcription-worker` y SSE publica avances parciales. El flujo legacy de audio completo
queda como fallback/migración.

```mermaid
sequenceDiagram
    actor Medico
    participant Browser as React (Browser)
    participant Backend as API Backend
    participant GCS as Cloud Storage
    participant Worker as transcription-worker Cloud Run
    participant Gemini as Vertex AI · Gemini

    rect rgb(240, 248, 255)
        note over Browser,GCS: Paso 1 — Grabacion por secciones
        Medico->>Browser: Inicia grabacion
        Browser->>Backend: POST /api/v1/transcription/sessions
        Backend-->>Browser: { session_id }
        loop Cada seccion independiente cerrada por pausa natural o maximo 33s
            Browser->>Browser: Guarda blob pendiente en IndexedDB
            Browser->>Backend: POST /api/v1/transcription/sessions/:id/sections/upload-url
            Backend-->>Browser: { upload_url, gcs_object_name }
            Browser->>GCS: PUT seccion (directo, signed URL)
            Browser->>Backend: POST /api/v1/transcription/sessions/:id/sections
            Backend-->>Browser: Registro durable
            Browser->>Browser: Borra blob local registrado
        end
    end

    rect rgb(255, 248, 240)
        note over Backend,Worker: Paso 2 — Transcripcion por seccion
        Backend->>Backend: Encola Cloud Task por seccion
        Backend->>Worker: POST /internal/transcription/tasks/sections/:section_id via OIDC
    end

    rect rgb(240, 255, 248)
        note over Worker,Gemini: Paso 3 — Procesamiento con IA
        Worker->>Worker: Silero ONNX VAD sobre seccion GCS
        Worker->>Gemini: async generate_content(gs:// seccion + prompt) si hay habla
        Gemini-->>Worker: Texto de seccion
        Worker->>Backend: Callback saneado con resultado de seccion
        Backend->>Backend: Guarda raw_transcript y estado
        Backend-->>Browser: SSE "transcription_update"
    end

    rect rgb(248, 240, 255)
        note over Browser,Browser: Paso 4 — Finalizacion deterministica
        Medico->>Browser: Detiene grabacion
        Browser->>Backend: POST /api/v1/transcription/sessions/:id/finish
        Backend->>Backend: Ordena secciones completas por section_index
        Backend->>Backend: Une transcriptos con deduplicacion ligera de overlap
        Backend->>Backend: Guarda documento y marca encuentro transcrito
        Backend-->>Browser: SSE "transcription_complete"
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
    participant DocWorker as document-generation-worker Cloud Run
    participant Gemini as Vertex AI · Gemini

    rect rgb(240, 248, 255)
        note over Browser,Backend: Paso 1 — Apertura de canal SSE
        Browser->>Backend: POST /api/v1/documents/:doc_id/sse-token
        Backend-->>Browser: { token } (5 min)
        Browser->>Backend: GET /api/v1/sse/documents/:id/:token
        note right of Browser: Conexión SSE abierta (streaming)
    end

    rect rgb(255, 248, 240)
        note over Browser,DocWorker: Paso 2 — Trigger de generación
        Medico->>Browser: Clic en "Generar Documento"
        Browser->>Backend: POST /api/v1/documents/generate
        Backend->>Backend: Valida permisos, template y transcripción
        Backend->>Backend: Encola Cloud Task con IDs, sin PHI
        Backend-->>Browser: 200 OK { process_id }
    end

    rect rgb(240, 255, 248)
        note over Backend,Gemini: Paso 3 — Generación con streaming
        Backend->>DocWorker: POST /internal/document-generation/tasks/:process_id via OIDC
        DocWorker->>Backend: POST /internal/document-generation/work-items/:process_id
        Backend-->>DocWorker: Contenido clínico + JWT callback
        DocWorker->>Gemini: generate_content(prompt, stream=True)

        loop Cada chunk de texto
            Gemini-->>DocWorker: chunk
            DocWorker->>Backend: POST /api/v1/documents/generation-chunk
            Backend-->>Browser: SSE "generation_chunk" { chunk }
        end
    end

    rect rgb(248, 240, 255)
        note over Backend,Browser: Paso 4 — Finalización
        DocWorker->>Backend: POST generation-chunk { is_complete: true }
        Backend->>Backend: Guarda documento completo en BD
        Backend-->>Browser: SSE "generation_complete"
    end
```

---

## 4. Componentes y Responsabilidades

| Componente                           | Stack                                   | Responsabilidad                                                                                                            |
| ------------------------------------ | --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| **Frontend** `webapp/`               | React 18, Vite, TypeScript, Tailwind    | SPA del médico. Maneja grabación por secciones, IndexedDB, UI del editor y conexión SSE.                                   |
| **API principal** `backend_fastapi/` | FastAPI, SQLAlchemy async, PostgreSQL   | API bajo `/api/v1`, orquestación, JWTs, hub SSE, callbacks y migraciones Alembic.                                          |
| **Worker transcripción** `transcription_worker/` | FastAPI, ONNX Runtime, Google Gen AI SDK | Recibe Cloud Tasks por sección, corre Silero VAD, transcribe con Gemini si hay habla y devuelve callbacks saneados a FastAPI. |
| **Worker generación** `document_generation_worker/` | FastAPI, Google Gen AI SDK | Recibe Cloud Tasks con IDs, pide work-items a FastAPI, genera documentos con Gemini streaming y devuelve chunks saneados. |
| **Copilot Agent** `copilot_agent/`   | Python, FastAPI, LangGraph              | Runtime del copiloto; broker hacia el API principal.                                                                       |
| **Cloud Storage**                    | GCS                                     | Almacena los audios clínicos. El frontend sube directo vía signed URL.                                                     |
| **Vertex AI · Gemini**               | Managed (GCP)                           | Modelo de IA para transcripción y generación de documentos clínicos.                                                       |
| **PostgreSQL**                       | Cloud SQL                               | Base de datos principal: encuentros, documentos, pacientes, plantillas.                                                    |

---

## 5. Puntos de Atención Arquitectónica

- **Hub SSE en memoria**: el hub en `backend_fastapi` usa memoria de proceso. Con múltiples réplicas en Cloud Run, un evento en la instancia A no llega a clientes en la B. Resolver con Redis o Pub/Sub antes de escalar a más de una instancia.
- **Transcripción near realtime con VAD**: el navegador usa VAD ligero basado en Web Audio para cerrar secciones en pausas naturales, con umbral base de `1s` de silencio estable (`pre-roll=400ms`, `tail=600ms`). Entre `20s` y `25s` reduce ese silencio a `500ms`, y entre `25s` y `33s` lo reduce a `350ms` para encontrar una pausa útil antes del corte forzado. Mantiene mínimo de `1s`, máximo forzado de `33s` y `overlap=400ms` solo en ese corte forzado. Si el VAD no inicia, el frontend vuelve al fallback por tiempo (`20s`).
- **Backend público + DB privada**: Cloud Run sigue público para la SPA, pero PostgreSQL queda aislado por IP privada y acceso vía Cloud SQL Auth Proxy + IAM DB auth.
- **Agent runtime separado**: LangGraph no vive dentro del backend principal. El backend hace de broker y conserva la autoridad clínica/transaccional.
- **Auth interna temporal del copiloto**: el API (FastAPI) y `copilot-agent-service` usan un `shared JWT` temporal en `local`/`stg`; ver deuda canónica en [`../debt/copilot-agent-runtime.md`](../debt/copilot-agent-runtime.md).
- **Audio no se borra al transcribir**: `audio_expires_at` controla el acceso lógico legacy por 24h, pero el blob en GCS se elimina por lifecycle a los 7 días salvo DELETE explícito. SSE no borra audio.
- **Workers privados IAM-auth**: los workers de transcripción y generación están desplegados con `--no-allow-unauthenticated`; Cloud Tasks los invoca con OIDC y los callbacks usan JWTs de vida corta. El `JWT_SECRET_KEY` no debe filtrarse.

---

## 6. Observabilidad y trazas

OpenTelemetry enlaza peticiones entre el API, workers y callbacks cuando el export está configurado (OTLP/Jaeger en local, Cloud Trace en GCP con `GOOGLE_CLOUD_PROJECT`). Los logs del backend incluyen `trace_id` / `span_id` para correlación. Detalle y variables: [`../backend/tracing.md`](../backend/tracing.md). Limitaciones: SSE (`EventSource` sin cabeceras W3C), subida directa a GCS con signed URL y ejecuciones posteriores de Cloud Tasks no continúan el mismo trace de extremo a extremo.

El baseline operativo todavía no está cerrado para launch: ver deuda canónica en [`../debt/observability-baseline.md`](../debt/observability-baseline.md).
