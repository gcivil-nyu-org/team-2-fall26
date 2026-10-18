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
        self.initial.setdefault('semester', f'{terms[term_index]} {today.year}')
        self.fields['name'].required = True
        self.fields['semester'].required = True
        self.fields['code'].required = False
        self.fields['name'].error_messages['required'] = 'Course name is required.'
        self.fields['semester'].error_messages['required'] = 'Semester is required.'


class AssignmentForm(forms.ModelForm):
    class Meta:
        model = Assignment
        fields = ['title', 'due_date']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Homework 1',
            }),
            'due_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
        }
