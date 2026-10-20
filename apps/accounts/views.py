from datetime import timedelta

from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.coursework.models import Assignment
from .forms import SignUpForm


def signup_view(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('accounts:dashboard')
    else:
        form = SignUpForm()
    return render(request, 'accounts/signup.html', {'form': form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect('accounts:login')


@login_required(login_url='accounts:login')
def dashboard_view(request):
    courses = request.user.courses.all()
    today = timezone.localdate()
    week_end = today + timedelta(days=7)
    assignments = Assignment.objects.owned_by(request.user)
    outstanding = assignments.outstanding()
    return render(request, 'accounts/dashboard.html', {
        'courses': courses,
        'course_count': courses.count(),
        'due_this_week_count': outstanding.filter(due_date__gte=today, due_date__lte=week_end).count(),
        'overdue_count': assignments.overdue().count(),
        'outstanding_assignments': outstanding.select_related('course'),
    })
