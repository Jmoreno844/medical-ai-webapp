# Visión General del Sistema

Este documento describe la arquitectura global de la plataforma, sus componentes principales y cómo interactúan entre sí.

## 1. Arquitectura de Alto Nivel

El sistema es una plataforma fullstack que combina un backend Django, funciones serverless en GCP y una SPA en React. La pieza central es el backend Django, que coordina la comunicación entre todos los demás servicios.

```mermaid
graph LR
    subgraph client ["Cliente"]
        Browser["React + Vite\n(SPA)"]
    end

    subgraph gcp ["Google Cloud Platform"]
        subgraph backend_run ["Cloud Run"]
            Django["Django Ninja API"]
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

    Browser -->|"REST + sesión"| Django
    Browser -->|"PUT audio directo"| GCS
    Browser -->|"SSE stream"| Django

    Django -->|"ORM"| PG
    Django -->|"signed URL"| GCS
    Django -->|"JWT + payload"| CF_Trans
    Django -->|"JWT + payload"| CF_Gen
    Django -->|"secrets"| SM

    CF_Trans -->|"gs:// URI"| GCS
    CF_Trans -->|"Gemini API"| Vertex
    CF_Trans -->|"PATCH Bearer JWT"| Django

    CF_Gen -->|"Gemini streaming"| Vertex
    CF_Gen -->|"chunks Bearer JWT"| Django
```

---

## 2. Flujo de Transcripción de Audio

El camino completo desde que el médico detiene la grabación hasta que el texto aparece en el editor.

```mermaid
sequenceDiagram
    actor Medico
    participant Browser as React (Browser)
    participant Django as Django API
    participant GCS as Cloud Storage
    participant CF as CF transcription-endpoint
    participant Gemini as Vertex AI · Gemini

    rect rgb(240, 248, 255)
        note over Browser,GCS: Paso 1 — Subida de audio
        Medico->>Browser: Detiene grabación
        Browser->>Django: POST /encounters/:id/audio/upload-url
        Django-->>Browser: { upload_url, filename }
        Browser->>GCS: PUT audio (directo, signed URL)
    end

    rect rgb(255, 248, 240)
        note over Browser,CF: Paso 2 — Inicio de transcripción
        Browser->>Django: POST /transcription/start
        Django->>Django: Genera JWT de servicio (15 min)
        Django->>CF: POST { audio_uri, auth_token }
        note right of CF: Llamada síncrona — Django espera
    end

    rect rgb(240, 255, 248)
        note over CF,Gemini: Paso 3 — Procesamiento con IA
        CF->>GCS: Lee audio (gs:// URI)
        CF->>Gemini: generate_content(audio + prompt)
        Gemini-->>CF: Texto transcrito
    end

    rect rgb(248, 240, 255)
        note over CF,Browser: Paso 4 — Actualización y notificación
        CF->>Django: PATCH /documents/by-function/:id { content }
        Django->>Django: Guarda en PostgreSQL
        Django-->>Browser: SSE evento "transcription_complete"
        CF->>Django: POST /transcription/notify-complete
        Django->>Django: Marca encuentro como transcrito
        CF-->>Django: 200 OK
        Django-->>Browser: 200 OK
    end
```

---

## 3. Flujo de Generación de Documentos

Genera un documento clínico (SOAP, nota de evolución, etc.) combinando la transcripción, el contexto del paciente y una plantilla, con streaming en tiempo real vía SSE.

```mermaid
sequenceDiagram
    actor Medico
    participant Browser as React (Browser)
    participant Django as Django API
    participant CF as CF document-workflow
    participant Gemini as Vertex AI · Gemini

    rect rgb(240, 248, 255)
        note over Browser,Django: Paso 1 — Apertura de canal SSE
        Browser->>Django: POST /generate-sse-token/:doc_id
        Django-->>Browser: { token } (5 min)
        Browser->>Django: GET /sse/document/:id/:token
        note right of Browser: Conexión SSE abierta (streaming)
    end

    rect rgb(255, 248, 240)
        note over Browser,CF: Paso 2 — Trigger de generación
        Medico->>Browser: Clic en "Generar Documento"
        Browser->>Django: POST /documents/generate
        Django->>Django: Valida permisos y genera JWT (30 min)
        Django->>CF: POST validate_only=true (síncrono)
        CF-->>Django: 200 OK
        Django-->>Browser: 200 OK { process_id }
        note right of Django: Lanza hilo background →
    end

    rect rgb(240, 255, 248)
        note over Django,Gemini: Paso 3 — Generación con streaming
        Django->>CF: POST payload completo (background)
        CF->>Gemini: generate_content(prompt, stream=True)

        loop Cada chunk de texto
            Gemini-->>CF: chunk
            CF->>Django: POST /documents/generation-chunk
            Django-->>Browser: SSE "generation_chunk" { chunk }
        end
    end

    rect rgb(248, 240, 255)
        note over Django,Browser: Paso 4 — Finalización
        CF->>Django: POST generation-chunk { is_complete: true }
        Django->>Django: Guarda documento completo en BD
        Django-->>Browser: SSE "generation_complete"
    end
```

---

## 4. Componentes y Responsabilidades

| Componente | Stack | Responsabilidad |
|------------|-------|-----------------|
| **Frontend** `webapp/` | React 18, Vite, TypeScript, Tailwind | SPA del médico. Maneja grabación, UI del editor y conexión SSE. |
| **Backend** `backend/` | Django Ninja, PostgreSQL | API REST central. Orquesta flujos, emite JWTs, mantiene hub SSE. |
| **CF Transcripción** | Python, Functions Framework | Recibe audio de GCS → llama a Gemini → devuelve texto a Django. |
| **CF Generación** | Python, Functions Framework | Recibe contexto+plantilla → streaming desde Gemini → envía chunks a Django. |
| **Cloud Storage** | GCS | Almacena los audios clínicos. El frontend sube directo vía signed URL. |
| **Vertex AI · Gemini** | Managed (GCP) | Modelo de IA para transcripción y generación de documentos clínicos. |
| **PostgreSQL** | Cloud SQL | Base de datos principal: encuentros, documentos, pacientes, plantillas. |

---

## 5. Puntos de Atención Arquitectónica

- **Hub SSE en memoria**: `apps/documents/services/sse_hub.py` usa estructuras en memoria. Con múltiples réplicas en Cloud Run, un evento emitido en la instancia A no llega a clientes SSE en la instancia B. Resolver con Redis o Pub/Sub en el futuro.
- **Llamada síncrona a CF de transcripción**: Django espera respuesta de la Cloud Function. Si Gemini tarda demasiado, el request del frontend puede agotar el timeout.
- **Audio no se borra al transcribir**: `audio_expires_at` controla el acceso vía API, pero el blob en GCS solo se elimina si el médico lo solicita explícitamente.
- **Cloud Functions `--allow-unauthenticated`**: La seguridad se delega enteramente en la validez del JWT del body. El `JWT_SECRET_KEY` no debe filtrarse.

---

## 6. Observabilidad y trazas

OpenTelemetry enlaza las peticiones **navegador (XHR/axios) → Django → Cloud Functions → callbacks Django** cuando el export está configurado (OTLP/Jaeger en local, Cloud Trace en GCP con `GOOGLE_CLOUD_PROJECT`). Los logs del backend incluyen `trace_id` / `span_id` para correlación. Detalle y variables: [`../backend/tracing.md`](../backend/tracing.md). Limitaciones: SSE (`EventSource` sin cabeceras W3C) y subida directa a GCS con signed URL no continúan el mismo trace de extremo a extremo.
