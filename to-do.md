Modelo OpenAI ficticio — providers.py:34 devuelve "gpt-5.4-mini", no existe. Si alguien arranca con COPILOT_LLM_PROVIDER_FAMILY=openai y sin COPILOT_PLANNER_MODEL, falla en la primera llamada.

\_derive_status tiene rama muerta — runtime.py:1020-1034: los dos return finales son "completed". Un run sin final_response, sin run_error y sin waiting_review queda marcado completed silenciosamente. Debería ser failed.

Duplicación de las 4 tools propose\_\* — tools.py:1703-1925: ~50 líneas casi idénticas × 4. Solo cambia el nombre de la operación. Se colapsa a una factory parametrizada.

Validadores duplicados en 3 archivos: \_is_valid_patch_preview, \_is_valid_patch_set_preview, PATCH_REQUIRED_FIELDS viven en nodes.py, tools.py y runtime.py. Cualquier cambio se desincroniza.

runtime.py (1254 líneas) hace demasiado — persistencia, normalización de patch_set, derivación de status, construcción de eventos (dos versiones — async y sync), HTTP. La duplicación entre create_run (sync) y run_graph_async es espejo y eventualmente divergirá.

Fallback que sintetiza propose_replace_span sin LLM — planner.py:761-775: tras 3 turnos vacíos, el runtime fabrica un tool call de edición. Si el doctor pidió clarificación y Gemini se trabó decidiendo, esto fuerza una propuesta no autorizada. Está gated por conds razonables pero sigue siendo un acto irreversible disparado por silencio del modelo.

datetime.utcnow() deprecado en backend_tools_client.py:187. Python ≥3.12 emite warning. Usa datetime.now(timezone.utc).

Retries sin backoff — \_invoke_with_retry(attempts=2) reintenta inmediato. Un 429 o un blip de red probablemente falla las 2 veces igual.

set_edit_plan documenta "máximo una vez por run" pero no lo aplica — el planner puede llamarla dos veces y sobreescribir el plan + el budget de patches.

No hay limpieza de runs huérfanos — si uvicorn muere durante un BackgroundTask, el row queda status='running' para siempre. No hay reaper.

Sin timeout sobre graph.astream — si el provider se cuelga, el run vive indefinidamente.

Tests sueltos en raíz: test_find_afc.py, test_get.py, test_invoke.py, test_models.py, test_parse.py, test_planner.py, test_tools.py — scripts exploratorios mezclados con tests/. Y copilot_runtime.db SQLite parece artefacto stale (prod usa Postgres).

\_default_selected_document_ids corta a [:2] arbitrariamente — en encounters con 3+ docs activos, descarta info silenciosamente.
