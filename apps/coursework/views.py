from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from .forms import AssignmentForm, CourseForm
from .models import Assignment, Course


def _owned_course(request, pk):
    return get_object_or_404(Course, pk=pk, owner=request.user)


def _owned_assignment(request, pk):
    return get_object_or_404(Assignment.objects.owned_by(request.user), pk=pk)


def _redirect_back(request, assignment):
    next_url = request.POST.get('next')
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect('coursework:course_detail', pk=assignment.course_id)


@login_required(login_url='accounts:login')
def course_create_view(request):
    if request.method == 'POST':
        form = CourseForm(request.POST)
        if form.is_valid():
            course = form.save(commit=False)
            course.owner = request.user
            course.save()
            return redirect('coursework:course_detail', pk=course.pk)
    else:
        form = CourseForm()
    return render(request, 'coursework/course_form.html', {'form': form})


@login_required(login_url='accounts:login')
def course_detail_view(request, pk):
    course = _owned_course(request, pk)
    assignments = course.assignments.all()
    return render(request, 'coursework/course_detail.html', {
        'course': course,
        'assignments': assignments,
    })


@login_required(login_url='accounts:login')
def assignment_create_view(request, pk):
    course = _owned_course(request, pk)
    if request.method == 'POST':
        form = AssignmentForm(request.POST)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.course = course
            assignment.save()
            return redirect('coursework:course_detail', pk=course.pk)
    else:
        form = AssignmentForm()
    return render(request, 'coursework/assignment_form.html', {
        'form': form,
        'course': course,
    })


@login_required(login_url='accounts:login')
@require_POST
def assignment_complete_view(request, pk):
    assignment = _owned_assignment(request, pk)
    assignment.mark_complete()
    return _redirect_back(request, assignment)


@login_required(login_url='accounts:login')
@require_POST
def assignment_reopen_view(request, pk):
    assignment = _owned_assignment(request, pk)
    assignment.reopen()
    return _redirect_back(request, assignment)


@login_required(login_url='accounts:login')
def completed_assignments_view(request):
    assignments = Assignment.objects.owned_by(request.user).completed().select_related('course')
    return render(request, 'coursework/completed_assignments.html', {
        'assignments': assignments,
    })
