# ADR-005: Aislamiento de Cargas de Trabajo de IA (LangGraph) en Cloud Functions

## Estatus

Propuesto

## Contexto

Con la introducción de la Fase 2 (Pipeline de Inteligencia con LangGraph para detección de códigos CIE-10, CUM y CUPS), necesitamos desplegar un ecosistema pesado de agentes. Este flujo utiliza Gemini 2.0 Flash, búsquedas vectoriales, _Fan-out / Fan-in_ y persistencia de memoria (PostgresSaver).

La API principal de la plataforma está desarrollada en Django (Cloud Run), diseñada para servir tráfico web (REST/SSE) con latencia baja y alta concurrencia. Surgió la interrogante de si la lógica de LangGraph debería integrarse dentro del monolito actual de Django o separarse en su propio servicio.

## Decisión

Hemos decidido **aislar completamente el workflow de los agentes (LangGraph) en un servicio independiente**, específicamente desplegado como una **Cloud Function (Gen 2)** dedicada (o un servicio de Cloud Run independiente).

El backend de Django se limitará a encolar la petición (vía Cloud Tasks, ver ADR-004) y recibir los resultados procesados mediante un webhook o polling.

## Justificación Técnica

1. **Perfiles de Recursos Incompatibles:**
   - **Backend (Django):** Optimizado para conexiones concurrentes, E/S intensiva (I/O bound) y SSE. Requiere poca RAM y CPU por request.
   - **Agentes (LangGraph):** Requieren procesamiento intensivo (CPU bound), mantienen estado extenso en memoria y pueden tardar entre 15 a 60 segundos por ejecución. Mezclarlos causaría que los agentes monopolicen los recursos, degradando el rendimiento general de la API (provocando latencia en tareas simples como la carga de paicentes o pérdida de conexiones SSE).

2. **Inflación del Contenedor y Cold Starts:**
   - El ecosistema de IA (`langchain`, `langgraph`, extensiones vectoriales) añade cientos de megabytes a la imagen del contenedor. Incluir esto en el backend principal afectaría significativamente los tiempos de arranque en frío (_cold starts_) de la API.

3. **Ciclo de Vida y Despliegues Independientes:**
   - El flujo heurístico de los agentes (ajuste de _prompts_, umbrales de similitud `< 0.90`, topología del grafo) es altamente iterativo y propenso a cambios frecuentes.
   - Aislar el servicio permite desplegar nuevas versiones de la IA sin redesplegar ni arriesgar el _core_ transaccional del sistema de salud (citas, usuarios, expedientes).

4. **Principio de Mínimo Privilegio:**
   - La Cloud Function de LangGraph puede operar bajo su propio Service Account de IAM, restringiendo estrictamente sus accesos a Vertex AI y a las tablas específicas de pgvector, sin exponer el resto de los secretos que maneja el backend.

## Consecuencias

### Positivas

- **Estabilidad:** El servicio principal no se ve afectado por picos de carga de procesamiento de IA.
- **Eficiencia en Costos:** Podemos configurar hardware especializado (ej. mayor asignación de memoria y CPU) _únicamente_ para las instancias que ejecutan LangGraph, sin sobredimensionar las instancias del servidor web.
- **Agilidad en Desarrollo:** Los equipos pueden modificar y testear los agentes de IA de forma independiente.

### Negativas / Retos

- **Mantenimiento Adicional:** Introduce un nuevo recurso en la infraestructura (Terraform/CI-CD) que debe monitorearse.
- **Lógica de Webhooks:** Obliga a mantener y versionar correctamente el contrato de datos (payloads) entre la Cloud Function y Django.

## Notas

La integración local o testing de este componente debe realizarse de manera aislada (mediante scripts en Python aislados o Jupyter Notebooks) antes de ser integrada al ciclo de CI/CD, para validar la latencia y la calidad de la estructuración JSON de los endpoints.
