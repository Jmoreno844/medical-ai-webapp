from ninja import Router, File, UploadedFile
from ninja.security import django_auth
from ninja.errors import HttpError
from ninja.responses import Response


router = Router()
