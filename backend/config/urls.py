from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from ninja import NinjaAPI
from apps.users.api import router as accounts_router
from apps.encuentro.api import router as encuentro_router
from apps.pacientes.api import router as pacientes_router
from apps.plantillas.api import router as plantillas_router
from django.conf import settings

# Replace the single router import with imports from the package
from apps.documentos.api import (
    base_router as documentos_base_router,
    documentos_callbacks_router,
    documentos_generation_router,
    sse_router,
)
from apps.generative_ai.api import router as generative_ai_router

api = NinjaAPI(
    title="Medical API",
    version="1.0.0",
    urls_namespace="medical_api",
    csrf=not getattr(settings, "ENVIRONMENT", "") == "dev",  # Disable in dev only
)


@api.get("/csrf")
@ensure_csrf_cookie
@csrf_exempt
def get_csrf_token(request):
    return HttpResponse()


# Replace the single router with the three separate routers
api.add_router("/", documentos_base_router)
api.add_router("/", sse_router)
api.add_router("/", documentos_callbacks_router)
api.add_router("/", documentos_generation_router)
api.add_router("/auth/", accounts_router)
api.add_router("/", encuentro_router)
api.add_router("/", pacientes_router)
api.add_router("/", plantillas_router)
api.add_router("/", generative_ai_router)

urlpatterns = [
    path("api/admin/", admin.site.urls),
    path("api/", api.urls),
    path("api/silk/", include("silk.urls", namespace="silk")),
]
