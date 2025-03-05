from django.contrib import admin
from django.urls import path
from ninja import NinjaAPI
from apps.users.api import router as accounts_router
from apps.encuentro.api import router as encuentro_router
from apps.pacientes.api import router as pacientes_router
from apps.plantillas.api import router as plantillas_router
from apps.documentos.api import router as documentos_router
from apps.generative_ai.api import router as generative_ai_router

api = NinjaAPI(
    title="Medical API",
    version="1.0.0",
    urls_namespace="medical_api",
)

api.add_router("/", documentos_router)
api.add_router("/auth/", accounts_router)
api.add_router("/", encuentro_router)
api.add_router("/", pacientes_router)
api.add_router("/", plantillas_router)
api.add_router("/", generative_ai_router)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
]
