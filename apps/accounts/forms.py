from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['email', 'password1', 'password2']

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        domain = email.rsplit('@', 1)[-1]
        if domain != 'nyu.edu' and not domain.endswith('.nyu.edu'):
            raise forms.ValidationError('Please sign up with your NYU email address (@nyu.edu).')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = user.email  # keeps Django's internal username populated + unique
        if commit:
            user.save()
        return user
