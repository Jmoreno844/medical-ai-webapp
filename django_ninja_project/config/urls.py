from django.contrib import admin
from django.urls import path
from ninja import NinjaAPI
from accounts.api import router as accounts_router

api = NinjaAPI(
    title="Medical API",
    version="1.0.0",
    urls_namespace="medical_api",
)

api.add_router("/auth/", accounts_router)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
]
