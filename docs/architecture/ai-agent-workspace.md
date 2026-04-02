# Arquitectura del Agente de IA (Medical Workspace Copilot)

## 1. Visión General

El Copiloto Clínico no es un servicio monolítico frontend. Responde a una arquitectura de **capas segregadas** diseñada para operar bajo normativas HIPAA, reducir latencia, minimizar el costo de tokens (Context Caching) y garantizar cero escrituras fantasmas o alucinaciones destructivas.

### Componentes Principales

1. **Frontend (React / Vite):**
   - **Responsabilidad:** Renderizado visual (Lexical), gestión de estados locales (Drafts, Tabs abiertas), UI del chat y revisión de parches (Accept/Reject).
   - **Restricción:** No posee lógica del LLM, no gestiona el contexto completo, no almacena keys, no consolida documentos masivos para enviarlos por red.

2. **Backend Transaccional (Django / Cloud Run):**
   - **Responsabilidad:** Fuente única de la verdad. Persistencia de `documents`, `snapshots`, seguridad, permisos y servicios de API (`DocumentOperationsService`).

3. **Agent Runtime (LangGraph / Cloud Run):**
   - **Responsabilidad:** Orquestación, memoria de sesión, toma de decisiones (Tools) y streaming de respuestas (SSE) al frontend.
   - **Estado:** Utiliza un _Checkpointer_ respaldado temporalmente en PostgreSQL (y a futuro en Redis) para recordar qué documentos leyó en turnos previos de la sesión.

---

## 2. Flujo de Datos y Optimización de LLMs

Para resolver el problema de contexto masivo (ej. transcripciones de 30 minutos = ~15k tokens) sin quebrar latencia ni presupuesto, empleamos **Context Caching** junto con lecturas progresivas:

### Patrón "Index First"

- El Frontend nunca sube archivos largos en los payloads de chat.
- El Frontend envía un `WorkspaceIndex` ligero: `[{ doc_id: "123", version: 2 }, ...]`.
- El Agente revisa su memoria interna para ver si ya procesó la versión 2. Si no, usa herramientas para recabar la información desde el Backend Transaccional.

### Context Caching (Vertex AI / Gemini)

- **El Problema:** Leer una transcripción en 10 interacciones de chat costaría 150,000 tokens de input.
- **La Solución:** Cuando la transcripción del encuentro entra en un estado "estable", el Backend crea un **Context Cache**.
- El Agente invoca al LLM pasando simplemente el `cache_id` y el prompt variable del usuario (además de la nota). Esto proporciona ahorros superiores al 60% en input cost y drástica reducción de latencia (TTFT) manteniendo **100% de la precisión**.

---

## 3. Políticas de Lectura y Escritura (Safety)

### Lectura Longitudinal vs. Activa

- **Encuentro Actual:** Se lee la transcripción completa mediante Context Caching.
- **Historia Clínica Pasada:** Jamás se envían decenas de audios crudos al agente. El Agente usa herramientas de resumen (`mode: summary`) sobre la tabla de metadatos/resúmenes derivados en PostgreSQL `document_summaries`.

### El Sistema de Patches (Escritura Segura)

El agente de IA **tiene prohibido escribir o sobreescribir** el contenido canónico directamente (Snapshot).

1. El Agente genera un `DocumentPatch`.
2. El sistema lo guarda en BD como `pending`.
3. El frontend lo renderiza como previsualización de bloque.
4. El médico audita: Acepta, Modifica o Rechaza el parche.
5. Sólo tras la aprobación (audit log) el parche impacta el `DocumentSnapshot`.

## 4. Checklist para Escalabilidad

- [ ] **Fase MVP:** LangGraph y Django pueden compartir infraestructura en Cloud Run y PostgreSQL como checkpointer.
- [ ] **Fase Escalamiento (Múltiples Réplicas):** Reemplazar estados en memoria y pub/sub SSE hacia Redis (Google Cloud Memorystore) para evitar pérdida de streams entre contadores concurrentes.
