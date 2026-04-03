# Proyecto AI Médico

Producto fullstack para documentación médica asistida por IA. El flujo principal es:

1. El médico crea un `Encuentro` y graba audio.
2. El frontend sube el audio directo a GCS con signed URL.
3. Django dispara la transcripción y la generación documental.
4. Cloud Functions llama a Gemini y devuelve resultados a Django.
5. El frontend recibe transcripción y generación por SSE.

## Mapa del repo

- `backend/` — API Django Ninja, modelos, auth, SSE y orquestación.
- `cloud_functions/` — transcripción y generación documental en GCP Functions.
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
make -C backend sync-dev
make -C backend db-up
make -C backend migrate
make -C backend runserver
make -C backend test
```

Frontend:
```bash
npm --prefix webapp install
npm --prefix webapp run dev
npm --prefix webapp run lint
npm --prefix webapp run build
```

Cloud Functions:
```bash
cp cloud_functions/functions/.env.example cloud_functions/functions/.env.local
docker compose -f cloud_functions/docker-compose.yml up --build
python -m pytest cloud_functions/functions/tests
```

Copilot agent:
```bash
docker compose -f copilot_agent/docker-compose.yml up --build
```

## Notas para iteración rápida con IA

- Usa [`AGENTS.md`](AGENTS.md) como contrato principal para agentes.
- La guía más útil para retomar contexto rápido es [`docs/architecture/repo-map.md`](docs/architecture/repo-map.md).
- `webapp/dist/`, `webapp/node_modules/`, `landing-page/.next/`, `landing-page/node_modules/`, `backend/.venv/`, `backend/logs/` e `infra/**/.terraform/` son artefactos locales, no fuente de verdad.
- No existe billing de producto dentro de la app hoy; el único “billing” del repo está en budgets/monitoring de Terraform.
- El runtime del copiloto debe vivir fuera del backend principal; usa `copilot_agent/` como base de ese servicio.

## Documentación

La entrada central está en [`docs/README.md`](docs/README.md).
