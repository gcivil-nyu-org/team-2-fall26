from django import forms


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
