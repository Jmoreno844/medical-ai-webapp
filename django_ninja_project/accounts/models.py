from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
import jwt
from datetime import datetime, timedelta
from django.conf import settings

class UserRole(models.TextChoices):
    MEDICO = "medico", "Médico"
    ADMINISTRADOR = "administrador", "Administrador"

class UserManager(BaseUserManager):
    def create_user(self, email, name, lastName, password=None, **extra_fields):
        if not email:
            raise ValueError('Users must have an email address')
        
        email = self.normalize_email(email)
        user = self.model(
            email=email,
            name=name,
            lastName=lastName,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, name, lastName, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', UserRole.ADMINISTRADOR)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
            
        return self.create_user(email, name, lastName, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=50)
    lastName = models.CharField(max_length=50)
    role = models.CharField(
        max_length=20, choices=UserRole.choices, default=UserRole.MEDICO
    )
    
    # Fields required by Django's admin and authentication
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    
    objects = UserManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name', 'lastName']
    
    def __str__(self):
        return f"{self.name} {self.lastName}"
    
    def get_full_name(self):
        return f"{self.name} {self.lastName}"
    
    def get_short_name(self):
        return self.name

