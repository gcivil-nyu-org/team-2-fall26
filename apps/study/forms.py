from django import forms

from .models import AvailabilityBlock


class AvailabilityBlockForm(forms.ModelForm):
    start_time = forms.TimeField(input_formats=['%H:%M'])
    end_time = forms.TimeField(input_formats=['%H:%M'])

    class Meta:
        model = AvailabilityBlock
        fields = ['weekday', 'start_time', 'end_time']

    def clean(self):
        data = super().clean()
        start, end = data.get('start_time'), data.get('end_time')
        if start is not None and end is not None and end <= start:
            self.add_error('end_time', 'End time must be after start time on the same day.')
        return data
