from django import forms
from django.conf import settings
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


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        self.fields['first_name'].error_messages['required'] = 'First name is required.'
        self.fields['last_name'].error_messages['required'] = 'Last name is required.'


class ProfilePictureForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['profile_picture']

    def clean_profile_picture(self):
        picture = self.cleaned_data['profile_picture']
        max_size = settings.MAX_PROFILE_PICTURE_SIZE
        if picture.size > max_size:
            raise forms.ValidationError(f'Image must be smaller than {max_size // (1024 * 1024)}MB.')
        return picture
