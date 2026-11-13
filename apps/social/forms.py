from django import forms

from .models import FoodPost


class SendFriendRequestForm(forms.Form):
    email = forms.EmailField(
        error_messages={
            'required': 'Enter the email address of the student you want to add.',
            'invalid': 'Enter a valid email address.',
        },
    )

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()


class RespondToFriendRequestForm(forms.Form):
    STATUS_CHOICES = [('accepted', 'Accepted'), ('declined', 'Declined')]

    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        error_messages={
            'required': 'Choose to accept or decline this request.',
            'invalid_choice': 'Choose to accept or decline this request.',
        },
    )


class SendDirectMessageForm(forms.Form):
    body = forms.CharField(
        max_length=2000,
        strip=True,
        error_messages={
            'required': 'Write a message before sending.',
            'max_length': 'Messages must be 2000 characters or fewer.',
        },
    )


class FoodPostForm(forms.ModelForm):
    # The author is deliberately not a form field: the view always sets it
    # from request.user, so a client can never post as someone else.
    class Meta:
        model = FoodPost
        fields = ['place_name', 'description', 'location', 'cuisine', 'rating']
        error_messages = {
            'place_name': {'required': 'Enter the name of the restaurant or food place.'},
            'description': {'required': 'Add a description or recommendation.'},
            'rating': {
                'invalid': 'Choose a rating from 1 to 5.',
                'min_value': 'Choose a rating from 1 to 5.',
                'max_value': 'Choose a rating from 1 to 5.',
            },
        }
