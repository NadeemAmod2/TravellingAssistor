from django.db import models
from django.contrib.auth.models import AbstractUser as DjangoAbstractUser
# Create your models here.

class mdl_user(DjangoAbstractUser):
    email = models.EmailField(verbose_name='email address', unique=True,
                              error_messages={'unique': "A user with that email already exists."})
    weight = models.IntegerField(blank = True, null = True)
    cost_gym = models.FloatField(blank = True, null = True)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS=["username"]
    class Meta:
        db_table = 'auth_user'

    def __str__(self):
        return self.email