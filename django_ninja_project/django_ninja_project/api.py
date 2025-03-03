from ninja import NinjaAPI
from apps.pacientes.api import router as pacientes_router

api = NinjaAPI(title="Medical API")

api.add_router("/pacientes/", pacientes_router)

# Add other routers as needed
