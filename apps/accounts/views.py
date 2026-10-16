from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
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
    return render(request, 'accounts/dashboard.html')
