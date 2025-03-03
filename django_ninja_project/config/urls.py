from django.contrib import admin
from django.urls import path
from ninja import NinjaAPI
from apps.users.api import router as accounts_router
from apps.encuentro.api import router as encuentro_router

api = NinjaAPI(
    title="Medical API",
    version="1.0.0",
    urls_namespace="medical_api",
)

api.add_router("/auth/", accounts_router)
api.add_router("/", encuentro_router)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
]
