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


def validate_student_email(email, exclude_pk=None):
    # One rule for every way an email gets onto an account: students signing
    # up, and administrators correcting an address (#54). Lower-cased because
    # sign-in looks the address up in lower case.
    email = email.lower()
    domain = email.rsplit('@', 1)[-1]
    if domain != 'nyu.edu' and not domain.endswith('.nyu.edu'):
        raise forms.ValidationError('Please sign up with your NYU email address (@nyu.edu).')
    if User.objects.filter(email__iexact=email).exclude(pk=exclude_pk).exists():
        raise forms.ValidationError('An account with this email already exists.')
    return email


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['email', 'password1', 'password2']

    def clean_email(self):
        return validate_student_email(self.cleaned_data['email'])

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


class NotificationPreferencesForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            'study_reminders_enabled', 'study_reminder_minutes',
            'deadline_reminders_enabled', 'deadline_reminder_hours',
            'friend_request_alerts_enabled', 'message_alerts_enabled',
        ]
