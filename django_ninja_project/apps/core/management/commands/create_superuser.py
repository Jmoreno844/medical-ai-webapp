# apps/core/management/commands/create_superuser.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
import os
from google.cloud import secretmanager


class Command(BaseCommand):
    help = "Creates a superuser using credentials from Google Secret Manager"

    def handle(self, *args, **options):
        User = get_user_model()

        try:
            # Access the Google Secret Manager client
            client = secretmanager.SecretManagerServiceClient()

            # Get the project ID from environment
            project_id = os.environ.get("GCP_PROJECT_ID", "medical-ai-web-app")

            # Access superuser email secret
            email_secret_name = (
                f"projects/{project_id}/secrets/DJANGO_SUPERUSER_EMAIL/versions/latest"
            )
            email_response = client.access_secret_version(
                request={"name": email_secret_name}
            )
            superuser_email = email_response.payload.data.decode("UTF-8")

            # Access superuser password secret
            password_secret_name = f"projects/{project_id}/secrets/DJANGO_SUPERUSER_PASSWORD/versions/latest"
            password_response = client.access_secret_version(
                request={"name": password_secret_name}
            )
            superuser_password = password_response.payload.data.decode("UTF-8")

            superuser_name = "juan"

            superuser_lastname = "moreno"

            # Check if superuser already exists
            exists = User.objects.filter(email=superuser_email).exists()

            if exists:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Superuser with email {superuser_email} already exists."
                    )
                )
                return

            # Create superuser if it doesn't exist
            User.objects.create_superuser(
                email=superuser_email,
                name=superuser_name,
                lastName=superuser_lastname,
                password=superuser_password,
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Superuser with email {superuser_email} created successfully."
                )
            )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error creating superuser: {str(e)}"))
