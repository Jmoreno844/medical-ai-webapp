import os

# Set the environment, default to 'development'
ENVIRONMENT = os.environ.get("DJANGO_ENVIRONMENT", "develop")

if ENVIRONMENT == "production":
    from .production import *
elif ENVIRONMENT == "test":
    from .test import *
else:
    from .develop import *
