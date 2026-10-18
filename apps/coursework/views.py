from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from .forms import AssignmentForm, CourseForm
from .models import Course


def _owned_course(request, pk):
    return get_object_or_404(Course, pk=pk, owner=request.user)


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
