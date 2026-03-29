# Mapa de renombrado a inglés (referencia técnica)

Este documento describe la correspondencia entre identificadores históricos (español o mixtos) y los **identificadores técnicos en inglés** tras el refactor. Las **explicaciones** están en español; los nombres de código, rutas y claims en las tablas se mantienen en inglés porque así quedó definido el contrato.

La **experiencia de usuario** (textos visibles en la app) sigue en español en el frontend.

## Apps Django

| Anterior (paquete) | Nuevo             |
| ------------------ | ----------------- |
| `apps.encuentro`   | `apps.encounters` |
| `apps.documentos`  | `apps.documents`  |
| `apps.pacientes`   | `apps.patients`   |
| `apps.plantillas`  | `apps.templates`  |

## Modelos

| Anterior          | Nuevo                  |
| ----------------- | ---------------------- |
| `Encuentro`       | `Encounter`            |
| `Documento`       | `Document`             |
| `Paciente`        | `Patient`              |
| `PacienteMedico`  | `PatientDoctor`        |
| `PlantillaBase`   | `BaseTemplate`         |
| `PlantillaDoctor` | `DoctorTemplate`       |
| `UsoPlantilla`    | `TemplateUsage`        |
| `TipoDocumento`   | `TemplateDocumentKind` |

## Campos (ejemplos representativos)

| Anterior              | Nuevo                                  |
| --------------------- | -------------------------------------- |
| `id_medico`           | `doctor` (FK)                          |
| `id_paciente`         | `patient` (FK)                         |
| `id_encuentro`        | `encounter` (FK)                       |
| `nombre_encuentro`    | `encounter_name`                       |
| `paciente_conectado`  | `patient_connected`                    |
| `nombre` (paciente)   | `name`                                 |
| `resumen`             | `summary`                              |
| `contenido`           | `content`                              |
| `fecha_creacion`      | `created_on` (fecha)                   |
| `fecha` (encuentro)   | `occurred_at`                          |
| `tipo` (documento)    | `kind`                                 |
| `id_plantilla_doctor` | `doctor_template` (FK)                 |
| `id_plantilla_base`   | `base_template` (FK)                   |
| `tipo_documento`      | `document_kind`                        |
| `contenido_base`      | `uses_base_content`                    |
| `veces_usada`         | `use_count`                            |
| `ultimo_uso`          | `last_used_at`                         |
| `id_plantilla`        | `doctor_template` (en `TemplateUsage`) |
| `User.lastName`       | `User.last_name`                       |
| `User.pacientes`      | `User.patients`                        |

## Valores almacenados (enumeraciones)

| Dominio           | Valores anteriores                               | Valores nuevos                                 |
| ----------------- | ------------------------------------------------ | ---------------------------------------------- |
| Tipo de documento | `contexto`, `transcripcion`, `plantilla`, `nota` | `context`, `transcription`, `template`, `note` |
| Tipo en plantilla | `nota`, `documento`, `otros`                     | `note`, `document`, `other`                    |
| Rol de usuario    | `medico`, `administrador`                        | `doctor`, `administrator`                      |

## Rutas REST (prefijo `/api/`)

| Ruta anterior                   | Ruta nueva                                  |
| ------------------------------- | ------------------------------------------- |
| `/encuentros`                   | `/encounters`                               |
| `/documento`                    | `/documents`                                |
| `/documento/encuentro/{id}`     | `/documents/encounter/{id}`                 |
| `/documento/{id}`               | `/documents/{id}`                           |
| `/documento_by_editor/{id}`     | `/documents/by-editor/{id}`                 |
| `/documento_by_function/{id}`   | `/documents/by-function/{id}`               |
| `/generate-sse-token/{id}`      | igual (id de documento)                     |
| `/sse/documento/{id}`           | `/sse/document/{id}`                        |
| `/paciente`                     | `/patients`                                 |
| `/paciente/{id}`                | `/patients/{id}`                            |
| `/pacientes/search`             | `/patients/search`                          |
| `/plantilla_doctor`             | `/doctor-templates`                         |
| `/plantillas_short`             | `/doctor-templates/short`                   |
| `/plantilla_doctor/{id}`        | `/doctor-templates/{id}`                    |
| `/plantilla_doctor/uso/{id}`    | `/doctor-templates/{id}/usage`              |
| `/plantillas/{id}` (DELETE)     | `/doctor-templates/{id}`                    |
| `/generar_url_audio/{id}`       | `/encounters/{id}/audio/upload-url`         |
| `/encuentros/audio_exists/{id}` | `/encounters/{id}/audio/exists`             |
| `/encuentros/delete_audio/{id}` | `DELETE /encounters/{id}/audio`             |
| `/obtener_url_audio/{id}`       | `/encounters/{id}/audio/gcs-uri`            |
| `/autorizar-documento/{id}`     | `/documents/{id}/transcription-token`       |
| `/iniciar_transcripcion`        | `/transcription/start`                      |
| `/auth/registro`                | `/auth/register`                            |
| `/generate-document`            | puede unificarse como `/documents/generate` |

Callbacks desde Cloud Functions hacia Django (ejemplos de alineación):

- `/document/generation-chunk` → `/documents/generation-chunk`
- `/notify/transcription-complete` → `/transcription/notify-complete`

## Claims JWT (servicio / SSE)

| Claim anterior | Claim nuevo   |
| -------------- | ------------- |
| `id_usuario`   | `user_id`     |
| `id_documento` | `document_id` |
| `id_proceso`   | `process_id`  |

## JSON entre Django y Cloud Functions

Las claves del cuerpo HTTP deben alinearse con el contrato en inglés, por ejemplo: `id_documento` → `document_id`, `documento_contexto` → `context_document`, etc. El detalle exacto vive en el código de `generation`, callbacks y `django_api` en Cloud Functions.

---

**Nota:** Este archivo es la referencia para el refactor de nombres técnicos. Si el equipo cambia el vocabulario en código, actualiza también este mapa. Para entender el **dominio clínico** en lenguaje natural, usa `database.md`, `flows.md` y `system_map.md` (texto explicativo en español donde aplica).
