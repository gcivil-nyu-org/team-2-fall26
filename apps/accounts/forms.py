from django import forms
from django.conf import settings
from django.contrib.auth.forms import UserCreationForm

from .models import User


class AccountActionForm(forms.Form):
    current_password = forms.CharField(strip=False, error_messages={'required': 'Enter your current password.'})
    confirmation = forms.CharField(error_messages={'required': 'Type the confirmation word to continue.'})

    def __init__(self, *args, user, action, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.action = action

    def clean_current_password(self):
        password = self.cleaned_data['current_password']
        if not self.user.check_password(password):
            raise forms.ValidationError('Your current password is incorrect.')
        return password

    def clean_confirmation(self):
        value = self.cleaned_data['confirmation']
        expected = 'DELETE' if self.action == 'delete' else 'DEACTIVATE'
        if value != expected:
            raise forms.ValidationError(f'Type {expected} to confirm.')
        return value


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
        fields = ['first_name', 'last_name', 'bio']
        error_messages = {
            'bio': {'max_length': 'Bio must be 300 characters or fewer.'},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        self.fields['first_name'].error_messages['required'] = 'First name is required.'
        self.fields['last_name'].error_messages['required'] = 'Last name is required.'


class PrivacySettingsForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['show_email', 'show_bio', 'show_profile_picture']


class ProfilePictureForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['profile_picture']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The model field is blank=True (a user may have no picture at all),
        # but this form is only ever used to submit a new upload. Without
        # this, an empty submission with no existing picture would reach
        # clean_profile_picture() with None and crash on `picture.size`
        # instead of failing validation cleanly.
        self.fields['profile_picture'].required = True

    def clean_profile_picture(self):
        picture = self.cleaned_data['profile_picture']
        max_size = settings.MAX_PROFILE_PICTURE_SIZE
        if picture.size > max_size:
            raise forms.ValidationError(f'Image must be smaller than {max_size // (1024 * 1024)}MB.')
        return picture
