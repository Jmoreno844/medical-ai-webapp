# Guía de Inicio Local (Onboarding)

Esta guía describe los pasos para levantar todo el ecosistema del Proyecto AI Médico en tu máquina local para desarrollo.

## Requisitos Previos

- **Docker** y **Docker Compose**
- **Python 3.12+** y **uv** (para el backend)
- **Node.js 20+** y **npm** (para el frontend)
- Cuenta de **Google Cloud** con un proyecto configurado (Vertex AI, Cloud Storage)
- **ngrok** (para recibir webhooks de Cloud Functions localmente)

---

## 1. Configuración de Variables de Entorno

### Backend
Copia el archivo de ejemplo y configura tus credenciales en `backend/.env`:
```bash
cd backend
cp .env.example .env
```
Asegúrate de llenar:
- `DJANGO_SECRET_KEY`
- `JWT_SECRET_KEY`
- `GCS_BUCKET_NAME`
- `GCP_STORAGE_SERVICE_ACCOUNT_KEY_PATH` (ruta absoluta al JSON de tu Service Account)

### Frontend
Copia el archivo de ejemplo en `webapp/.env.local`:
```bash
cd webapp
cp .env.example .env.local
```
Por defecto, `VITE_API_URL=http://localhost:8000`.

### Cloud Functions
Crea un archivo `.env` en `cloud_functions/` con:
```env
GCP_PROJECT=tu-proyecto-gcp
GCP_REGION=us-central1
GEMINI_MODEL=gemini-1.5-pro
DJANGO_API_BASE_URL=http://host.docker.internal:8000  # Para que el contenedor vea a Django
```

---

## 2. Levantar la Base de Datos

El backend usa PostgreSQL. Puedes levantarlo fácilmente con Docker Compose desde la carpeta `backend/`:

```bash
cd backend
make db-up
# o manualmente: docker compose up -d db
```

---

## 3. Iniciar el Backend (Django)

Con la base de datos corriendo, instala las dependencias y corre las migraciones:

```bash
cd backend
uv sync
uv run python manage.py migrate
uv run python manage.py createsuperuser  # Opcional, para acceder al admin
uv run python manage.py runserver 0.0.0.0:8000
```

---

## 4. Iniciar el Frontend (React/Vite)

En otra terminal:

```bash
cd webapp
npm install
npm run dev
```
El frontend estará disponible en `http://localhost:5173`.

---

## 5. Emular Cloud Functions Localmente

Las Cloud Functions se pueden correr localmente usando Docker. Esto es útil para probar la integración con Gemini sin desplegar a GCP.

```bash
cd cloud_functions
docker-compose up --build
```
Esto levantará el emulador de Functions Framework en el puerto `8080`.

### Configurar ngrok para Webhooks (Opcional pero recomendado)

Si las Cloud Functions locales necesitan enviar peticiones de vuelta al backend de Django (callbacks), y estás usando herramientas externas o probando flujos complejos, puedes exponer tu backend local con ngrok:

```bash
ngrok http 8000
```

Luego, actualiza `DJANGO_API_BASE_URL` en el `.env` de `cloud_functions/` con la URL de ngrok (ej. `https://1234-abcd.ngrok.io`) y reinicia el contenedor de Cloud Functions.

---

## Resumen de Puertos Locales

- **`5173`**: Frontend (Vite)
- **`8000`**: Backend (Django API)
- **`5432`**: Base de Datos (PostgreSQL en Docker)
- **`8080`**: Cloud Functions (Emulador local)
