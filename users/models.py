from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    REQUIRED_FIELDS = ['email']
    
    def __str__(self):
        return self.username