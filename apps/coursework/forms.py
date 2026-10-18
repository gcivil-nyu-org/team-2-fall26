from django import forms
from .models import Course, Assignment


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ['name', 'code', 'semester']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Software Engineering',
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'CSCI-UA 101',
            }),
            'semester': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Fall 2026',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
