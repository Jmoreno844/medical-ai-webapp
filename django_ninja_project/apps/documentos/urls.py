from ninja import Router
from apps.documentos.api import router as documentos_router

router = Router()
router.add_router("", documentos_router)
