from django.contrib.auth.forms import UserCreationForm as DjangoUserCreationForm, UserChangeForm as DjangoUserChangeForm

from app_user.models import mdl_user
from django import forms

class PersonalInfoForm(forms.ModelForm):
    class Meta:
        model=mdl_user
        fields=("weight", "cost_gym", )
class UserSignupForm(DjangoUserCreationForm):
    first_name = forms.CharField(max_length=50, required=True)
    last_name = forms.CharField(max_length=150, required=True)
    
    class Meta:
        model = mdl_user
        fields = ('first_name','last_name', 'email', 'password1', 'password2', )