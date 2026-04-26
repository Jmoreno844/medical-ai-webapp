# ADR-005: Aislamiento de Cargas de Trabajo de IA (LangGraph) en Cloud Run Dedicado

## Estatus

Aceptado

## Contexto

Con la introducción del copiloto clínico read-only y su evolución futura hacia `patch -> review -> apply`, necesitamos desplegar un ecosistema de agentes separado del backend transaccional. Este flujo utiliza LangGraph, streaming brokered, tools internas read-only y persistencia de memoria (`PostgresSaver`).

La API principal de la plataforma estaba en Django cuando se aceptó este ADR; hoy vive en FastAPI (Cloud Run), diseñada para servir tráfico web (REST/SSE) con latencia baja y alta concurrencia. Surgió la interrogante de si la lógica de LangGraph debería integrarse dentro del API principal o separarse en su propio servicio.

## Decisión

Hemos decidido **aislar completamente el workflow de los agentes (LangGraph) en un servicio independiente desplegado como Cloud Run**, bajo el boundary `copilot-agent-service`.

El backend principal sigue siendo el broker seguro:

- autentica al usuario
- valida permisos
- decide el `thread_id`
- llama al agent runtime por contrato interno
- expone el stream seguro al frontend
- conserva la autoridad para aplicar patches clínicos

## Justificación Técnica

1. **Perfiles de Recursos Incompatibles:**
   - **Backend (FastAPI):** Optimizado para conexiones concurrentes, E/S intensiva (I/O bound) y SSE. Requiere poca RAM y CPU por request.
   - **Agentes (LangGraph):** Requieren procesamiento intensivo (CPU bound), mantienen estado extenso en memoria y pueden tardar entre 15 a 60 segundos por ejecución. Mezclarlos causaría que los agentes monopolicen los recursos, degradando el rendimiento general de la API (provocando latencia en tareas simples como la carga de paicentes o pérdida de conexiones SSE).

2. **Inflación del Contenedor y Cold Starts:**
   - El ecosistema de IA (`langchain`, `langgraph`, extensiones vectoriales) añade cientos de megabytes a la imagen del contenedor. Incluir esto en el backend principal afectaría significativamente los tiempos de arranque en frío (_cold starts_) de la API.

3. **Ciclo de Vida y Despliegues Independientes:**
   - El flujo heurístico de los agentes (ajuste de _prompts_, umbrales de similitud `< 0.90`, topología del grafo) es altamente iterativo y propenso a cambios frecuentes.
   - Aislar el servicio permite desplegar nuevas versiones de la IA sin redesplegar ni arriesgar el _core_ transaccional del sistema de salud (citas, usuarios, expedientes).

4. **Principio de Mínimo Privilegio:**
   - El `copilot-agent-service` opera bajo su propio Service Account de IAM, restringiendo estrictamente sus accesos a Vertex AI, Secret Manager y Cloud SQL para checkpoints/memoria, sin exponer el resto de los secretos que maneja el backend.

5. **Durable Execution Real:**
   - Cloud Run es efímero/stateless. Si el grafo necesita reanudación, interrupts o memoria por thread, el checkpointer no puede vivir en RAM del contenedor.
   - Por eso se adopta una base de datos externa para el state del runtime.

## Consecuencias

### Positivas

- **Estabilidad:** El servicio principal no se ve afectado por picos de carga de procesamiento de IA.
- **Eficiencia en Costos:** Podemos configurar hardware especializado (ej. mayor asignación de memoria y CPU) _únicamente_ para las instancias que ejecutan LangGraph, sin sobredimensionar las instancias del servidor web.
- **Agilidad en Desarrollo:** Los equipos pueden modificar y testear los agentes de IA de forma independiente.
- **Mejor Boundary Operativo:** El ciclo de deploy del runtime del agente queda separado del deploy del backend clínico.

### Negativas / Retos

- **Mantenimiento Adicional:** Introduce un nuevo recurso en la infraestructura (Terraform/CI-CD) que debe monitorearse.
- **Nuevo Servicio e Infra:** Añade un segundo Cloud Run, una SA nueva, DB lógica separada y workflow CI/CD independiente.
- **Contratos Internos:** Obliga a mantener y versionar correctamente el contrato `backend broker <-> agent runtime`.

## Notas

La integración local de este componente debe ejecutarse como servicio propio (`copilot_agent/`) con Docker y configuración independiente del backend principal.
