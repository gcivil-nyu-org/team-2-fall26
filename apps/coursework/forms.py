from datetime import datetime

from django import forms
from django.utils import timezone
from .models import Course, Assignment


class CourseForm(forms.ModelForm):
    semester = forms.ChoiceField(
        widget=forms.Select(attrs={
            'class': 'form-select',
        }),
        error_messages={'required': 'Semester is required.'},
    )

    class Meta:
        model = Course
        fields = ['name', 'code', 'semester']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter course name',
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.localdate()
        terms = ('Spring', 'Summer', 'Fall')
        term_index = 0 if today.month <= 5 else 1 if today.month <= 8 else 2
        current = today.year * len(terms) + term_index
        self.fields['semester'].choices = [
            (
                f'{terms[index]} {year}',
                f'{terms[index]} {year}' + (' (current)' if (year, index) == (today.year, term_index) else ''),
            )
            for year, index in (divmod(current + offset, len(terms)) for offset in (-1, 0, 1))
        ]
        # Keep an edited course's semester selectable after it ages out of the window.
        saved = self.instance.semester if self.instance.pk else ''
        if saved and saved not in dict(self.fields['semester'].choices):
            self.fields['semester'].choices.insert(0, (saved, saved))
        self.initial.setdefault('semester', f'{terms[term_index]} {today.year}')
        self.fields['name'].required = True
        self.fields['semester'].required = True
        self.fields['code'].required = False
        self.fields['name'].error_messages['required'] = 'Course name is required.'
        self.fields['semester'].error_messages['required'] = 'Semester is required.'


class DeadlineField(forms.DateTimeField):
    def to_python(self, value):
        # Django also accepts ISO date-only input; require an explicit time.
        if isinstance(value, str) and value.strip():
            try:
                datetime.strptime(value, '%Y-%m-%dT%H:%M')
            except ValueError:
                raise forms.ValidationError(self.error_messages['invalid'], code='invalid')
        return super().to_python(value)


class AssignmentForm(forms.ModelForm):
    due_date = DeadlineField(
        label='Deadline',
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M',
            attrs={'class': 'form-control', 'type': 'datetime-local'},
        ),
        error_messages={
            'required': 'A deadline date and time are required.',
            'invalid': 'Enter a valid deadline date and time.',
        },
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['due_date'].help_text = f'Time zone: {timezone.get_current_timezone_name()}.'

    class Meta:
        model = Assignment
        fields = ['title', 'due_date', 'description']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Homework 1',
            }),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
