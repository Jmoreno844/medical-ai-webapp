# Backend

El backend es la API central del sistema. Orquesta auth, encuentros, documentos, SSE, callbacks y el acceso a GCS.

## Leer primero

- [`../docs/backend/README.md`](../docs/backend/README.md)
- [`apps/documents/README.md`](apps/documents/README.md)

## Comandos comunes

```bash
make -C backend help
make -C backend sync-dev
make -C backend db-up
make -C backend migrate
make -C backend runserver
make -C backend check
```

## Mapa rápido

- `apps/` — dominios de negocio
- `config/settings/` — entornos y logging
- `utils/` — JWT, auth y helpers compartidos
- `scripts/` — utilidades locales y de Docker

## Notas de mantenimiento

- `apps/documents/` y `apps/generative_ai/` comparten el flujo de IA, pero no son intercambiables: documentos maneja SSE/generación; `generative_ai` inicia transcripción.
- `apps/encounters/services/storage.py` es el lugar correcto para cambios de GCS, signed URLs o credenciales.
- Antes de tocar auth, tokens o callbacks, revisa [`../docs/backend/auth-and-jwt.md`](../docs/backend/auth-and-jwt.md).
