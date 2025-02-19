from django.contrib.auth.models import AbstractUser
from django.db import models


class UserRole(models.TextChoices):
    MEDICO = "medico", "Médico"
    ADMINISTRADOR = "administrador", "Administrador"


class User(AbstractUser):
    name = models.CharField(max_length=50)
    lastName = models.CharField(max_length=50)
    email = models.EmailField(unique=True)
    role = models.CharField(
        max_length=20, choices=UserRole.choices, default=UserRole.MEDICO
    )

    # Add related_name to avoid clashes
    groups = models.ManyToManyField(
        "auth.Group",
        related_name="custom_user_set",
        blank=True,
        verbose_name="groups",
    )
    user_permissions = models.ManyToManyField(
        "auth.Permission",
        related_name="custom_user_set",
        blank=True,
        verbose_name="user permissions",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name", "lastName"]

    def __str__(self):
        return f"{self.name} {self.lastName}"
