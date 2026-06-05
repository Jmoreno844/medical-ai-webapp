# Proyecto AI Médico

Producto fullstack para documentación médica asistida por IA. El flujo principal es:

1. El médico crea un `Encuentro` y graba audio.
2. El frontend sube el audio directo a GCS con signed URL.
3. FastAPI dispara la transcripción y la generación documental.
4. Los workers privados en Cloud Run procesan transcripción y generación documental.
5. El frontend recibe transcripción y generación por SSE.

## Mapa del repo

- `backend_fastapi/` — API FastAPI, modelos SQLAlchemy, auth, SSE, orquestación y migraciones Alembic.
- `transcription_worker/` — worker Cloud Run para transcripción por secciones.
- `document_generation_worker/` — worker Cloud Run para generación documental.
- `copilot_agent/` — runtime dedicado del copiloto clínico basado en LangGraph.
- `webapp/` — SPA React/Vite usada por el médico.
- `infra/` — Terraform, IAM, Cloud Run, Cloud SQL, buckets, budgets.
- `landing-page/` — sitio de marketing separado del producto principal.
- `docs/` — documentación operativa y arquitectónica.

## Leer primero

- [`docs/architecture/repo-map.md`](docs/architecture/repo-map.md)
- [`docs/architecture/system-overview.md`](docs/architecture/system-overview.md)
- [`docs/setup-local.md`](docs/setup-local.md)
- [`docs/backend/auth-and-jwt.md`](docs/backend/auth-and-jwt.md)
- [`docs/backend/database.md`](docs/backend/database.md)

## Comandos comunes

Backend:
```bash
cd backend_fastapi
uv sync --group dev
uv run alembic upgrade head
ENVIRONMENT=local uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
uv run pytest -q
```

Frontend:
```bash
npm --prefix webapp install
npm --prefix webapp run dev
npm --prefix webapp run lint
npm --prefix webapp run build
```

Workers:
```bash
python -m pytest transcription_worker/tests
python -m pytest document_generation_worker/tests
```

Copilot agent:
```bash
docker compose -f copilot_agent/docker-compose.yml up --build
```

## Notas para iteración rápida con IA

- Usa [`AGENTS.md`](AGENTS.md) como contrato principal para agentes.
- La guía más útil para retomar contexto rápido es [`docs/architecture/repo-map.md`](docs/architecture/repo-map.md).
- `webapp/dist/`, `webapp/node_modules/`, `landing-page/.next/`, `landing-page/node_modules/`, `backend_fastapi/.venv/` e `infra/**/.terraform/` son artefactos locales, no fuente de verdad.
- No existe billing de producto dentro de la app hoy; el único “billing” del repo está en budgets/monitoring de Terraform.
- El runtime del copiloto debe vivir fuera del backend principal; usa `copilot_agent/` como base de ese servicio.

## Documentación

La entrada central está en [`docs/README.md`](docs/README.md).
