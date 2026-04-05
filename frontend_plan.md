Plan de implementación: Side Chat v2 + Patch Review UX
Estado actual (punto de partida)
Componente Estado Problema
CopilotSidePanel.tsx Tabs iguales (Copilot / Debug) Se ve como panel técnico, no como herramienta para doctores
CopilotSideChatPanel.tsx 310 líneas, chat + review todo junto Monolítico; mensajes son divs planos sin markdown; review es una lista plana de patches sin agrupación por sección
PatchSetEditorView.tsx Side-by-side viejo/nuevo con react-simple-code-editor + Prism Lo reemplazaremos con inline highlights V1; monoespacio ("Fira Code") no es apropiado para texto clínico
useCopilotPanelController.ts Maneja todo el estado y acciones Reutilizable tal cual — los cambios son solo de presentación
Layout Panel 380-420px fijo a la derecha OK, no cambia
Alcance del cambio
Tres tracks paralelos que se pueden implementar en fases:

Fase 1: Chat bonito + debug toggle (2-3 días)
Meta: El side chat se ve como un producto para doctores, no como un debug panel.

1.1 Renombrar carpeta y limpiar naming
CopilotSidePanel.tsx → CopilotPanel.tsx
CopilotSideChatPanel.tsx → se divide (ver 1.3)
CopilotDebugPanel.tsx → queda igual (solo se esconde)
useCopilotPanelController.ts → queda igual (la lógica no cambia)
1.2 Panel exterior: debug como botón pequeño
Reemplazar el tab Copilot | Debug por:

El debug toggle es un icono pequeño (bug/wrench) en el header, no un tab prominente
Default: chat. Click: debug. Click de nuevo: chat.
El header dice "Asistente clínico" en español, no "Copilot Panel"
1.3 Dividir CopilotSideChatPanel.tsx en componentes
El archivo monolítico de 310 líneas se divide en:

1.4 Burbujas de chat rediseñadas
User bubble:

Assistant bubble:

Tool call (colapsado por default):

Markdown rendering: Agregar react-markdown + remark-gfm para renderizar respuestas del asistente con formato (listas, bold, headers).

1.5 Input mejorado
Auto-grow del textarea (1 línea a 4 max)
Sin placeholder prefijado con instrucciones predeterminadas
Sin botones "Init chat" / "Refresh" visibles (la sesión se inicializa automáticamente al primer envío; refresh es interno)
Sin metadatos técnicos (run_id, thread_id, status) — eso va al debug view
1.6 Estado "pensando"
Reemplazar la barra azul genérica con typing indicator:

Fase 2: Tarjeta de review en el chat (2-3 días)
Meta: Cuando el agente propone cambios, el chat muestra una tarjeta de review agrupada por secciones en lugar de una lista plana.

2.1 Display names de secciones
2.2 PatchReviewCard.tsx
Reemplaza el bloque monolítico {reviewPatchSet && (...)} actual.

2.3 PatchSectionGroup.tsx
2.4 Agrupación lógica
Fase 3: Inline diff V1 en el editor (3-4 días)
Meta: Los patches se muestran inline en el documento de Lexical, no en un PatchSetEditorView separado.

3.1 Nuevo plugin de Lexical: PatchHighlightPlugin.tsx
Este plugin:

Escucha patchSetStore.activePatchSetId + patches del store
Para cada patch con resolvedRange, inserta decorations de Lexical en las posiciones correspondientes
Usa DecoratorNode o $createRangeSelection() para marcar las zonas
Reglas V1 por operation_type:

Tipo Vista en editor
replace_span Texto viejo con fondo rojo suave tachado → texto nuevo con fondo verde suave. Botones ✓ ✗ en margen
insert_before / insert_after_span Bloque verde insertado con icono ↓. Botones ✓ ✗
delete_span Texto tachado en rojo. Botones ✓ ✗
rewrite_document Banner arriba "Reescritura completa propuesta" — review en chat, no inline
Decoración visual:

3.2 Barra de navegación de cambios
Cuando hay 3+ patches, mostrar una barra flotante arriba del editor:

goToNext / goToPrev hacen scroll del editor hasta el siguiente patch y lo seleccionan.

3.3 Retirar PatchSetEditorView.tsx
Una vez que PatchHighlightPlugin funcione, PatchSetEditorView.tsx (que renderiza todo el contenido en react-simple-code-editor con fuente monoespaciada) se elimina. La decisión en TextArea.tsx cambia:

3.4 Interacción documento ↔ chat
La tarjeta de review en el chat y los highlights en el editor están sincronizados:

Click ↗ ir en la tarjeta → scroll del editor a esa sección (via patchSetStore.setSelectedPatch + plugin reacts)
Click ✓/✗ en el editor → actualiza patchSetStore → tarjeta refleja el cambio
Click ✓/✗ en la tarjeta → actualiza patchSetStore → highlight cambia (verde/rojo/desaparece)
Estado compartido: patchSetStore es la fuente de verdad para ambas superficies. No duplicar estado.

Fase 4: Polish (1-2 días)
Animaciones: Transición suave cuando un patch se acepta/rechaza (fade out del highlight)
Auto-scroll: Al recibir un patch set, scroll automático al primer patch
Responsive: En mobile, la tarjeta de review del chat se expande full-width; los botones ✓ ✗ inline tienen zona de tap más grande
Accesibilidad: role="alert" en la tarjeta de review, aria-label en los botones
Error states: Si el anchor resolve falla (sin resolvedRange), mostrar el patch solo en la tarjeta del chat, no inline
Dependencias a instalar
react-markdown + remark-gfm: markdown rendering en burbujas del assistant
lucide-react: iconos consistentes (Sparkles, Bug, Send, Check, X, ChevronDown, Edit, etc.)
Verificar si lucide-react ya está:

lucide-react ya presente. Solo falta react-markdown + remark-gfm.

Archivos que se tocan
Archivo Acción Fase
features/copilotDebug/ (carpeta) Rename → features/copilotChat/ 1
CopilotSidePanel.tsx Reescribir → CopilotPanel.tsx (header + debug toggle) 1
CopilotSideChatPanel.tsx Dividir en 6 componentes (ChatBody, ChatBubble, etc.) 1
CopilotDebugPanel.tsx Sin cambios internos, solo se esconde tras toggle 1
types.ts Agregar SECTION_DISPLAY_NAMES, section en types 2
Nuevo: PatchReviewCard.tsx Tarjeta de review con secciones 2
Nuevo: PatchSectionGroup.tsx Grupo de patches por sección 2
PatchSetEditorView.tsx Eliminar (reemplazado por PatchHighlightPlugin) 3
Nuevo: PatchHighlightPlugin.tsx Decorations inline en Lexical 3
Nuevo: PatchNavigationBar.tsx Nav bar ◀ ▶ arriba del editor 3
TextArea.tsx Cambiar rendering de patch_review mode 3
EncuentroDetailPage.tsx Update import de CopilotSidePanel → CopilotPanel 1
Lo que NO cambia
useCopilotPanelController.ts — toda la lógica de sesión, envío, review, finalize queda igual
api.ts — endpoints sin cambios
Stores de workspace (patchSetStore, documentDerivedStore, etc.) — sin cambios
applyCopilotPatchToWorkspace.ts — sin cambios
Backend — cero cambios, el section, affected_sections, edit_scope, old_text, new_text ya llegan en el payload
