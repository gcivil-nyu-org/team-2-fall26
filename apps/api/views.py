import json
from datetime import timedelta

from django.contrib.auth import authenticate, login, logout
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.forms import SignUpForm
from apps.coursework.forms import AssignmentForm, CourseForm
from apps.coursework.models import Assignment, Course


def _json_body(request):
    try:
        return json.loads(request.body or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _errors(form):
    return {
        field: [item['message'] for item in messages.get_json_data()]
        for field, messages in form.errors.items()
    }


def _unauthorized():
    return JsonResponse({'detail': 'Authentication required.'}, status=401)


def _user_payload(user):
    return {'id': user.pk, 'email': user.email}


def _course_payload(course, include_assignments=False):
    data = {
        'id': course.pk,
        'name': course.name,
        'code': course.code,
        'semester': course.semester,
        'assignment_count': getattr(course, 'assignment_count', course.assignments.count()),
    }
    if include_assignments:
        data['assignments'] = [_assignment_payload(item) for item in course.assignments.all()]
    return data


def _assignment_payload(assignment):
    due_date = timezone.localtime(assignment.due_date).isoformat() if assignment.due_date else None
    completed_at = timezone.localtime(assignment.completed_at).isoformat() if assignment.completed_at else None
    return {
        'id': assignment.pk,
        'title': assignment.title,
        'description': assignment.description,
        'due_date': due_date,
        'status': assignment.status,
        'completed_at': completed_at,
        'is_overdue': assignment.is_overdue,
        'course': {
            'id': assignment.course_id,
            'name': assignment.course.name,
            'code': assignment.course.code,
        },
    }


def _semester_payload(instance=None):
    form = CourseForm(instance=instance)
    selected = form['semester'].value()
    return {
        'choices': [{'value': value, 'label': label} for value, label in form.fields['semester'].choices],
        'default': selected,
    }


@ensure_csrf_cookie
@require_GET
def session_view(request):
    return JsonResponse({
        'authenticated': request.user.is_authenticated,
        'user': _user_payload(request.user) if request.user.is_authenticated else None,
    })


@require_POST
def login_view(request):
    body = _json_body(request)
    if body is None:
        return JsonResponse({'detail': 'Invalid JSON.'}, status=400)
    email = str(body.get('email', '')).strip().lower()
    user = authenticate(request, username=email, password=body.get('password', ''))
    if user is None:
        return JsonResponse({'errors': {'non_field_errors': ['The email or password is incorrect.']}}, status=400)
    login(request, user)
    return JsonResponse({'user': _user_payload(user)})


@require_POST
def signup_view(request):
    body = _json_body(request)
    if body is None:
        return JsonResponse({'detail': 'Invalid JSON.'}, status=400)
    form = SignUpForm({
        'email': body.get('email', ''),
        'password1': body.get('password', ''),
        'password2': body.get('password_confirm', ''),
    })
    if not form.is_valid():
        return JsonResponse({'errors': _errors(form)}, status=400)
    user = form.save()
    login(request, user)
    return JsonResponse({'user': _user_payload(user)}, status=201)


@require_POST
def logout_view(request):
    logout(request)
    return JsonResponse({'ok': True})


@require_GET
def dashboard_view(request):
    if not request.user.is_authenticated:
        return _unauthorized()
    now = timezone.now()
    week_end = now + timedelta(days=7)
    assignments = Assignment.objects.owned_by(request.user)
    outstanding = assignments.outstanding().select_related('course')
    courses = request.user.courses.annotate(assignment_count=Count('assignments'))
    return JsonResponse({
        'user': _user_payload(request.user),
        'metrics': {
            'courses': courses.count(),
            'due_this_week': outstanding.filter(due_date__gte=now, due_date__lte=week_end).count(),
            'overdue': assignments.overdue().count(),
        },
        'courses': [_course_payload(course) for course in courses],
        'assignments': [_assignment_payload(item) for item in outstanding],
    })


@require_http_methods(['GET', 'POST'])
def courses_view(request):
    if not request.user.is_authenticated:
        return _unauthorized()
    if request.method == 'GET':
        courses = request.user.courses.annotate(assignment_count=Count('assignments'))
        return JsonResponse({
            'courses': [_course_payload(course) for course in courses],
            'semester': _semester_payload(),
        })
    body = _json_body(request)
    if body is None:
        return JsonResponse({'detail': 'Invalid JSON.'}, status=400)
    form = CourseForm(body)
    if not form.is_valid():
        return JsonResponse({'errors': _errors(form)}, status=400)
    course = form.save(commit=False)
    course.owner = request.user
    course.save()
    return JsonResponse({'course': _course_payload(course)}, status=201)


@require_http_methods(['GET', 'PUT'])
def course_view(request, pk):
    if not request.user.is_authenticated:
        return _unauthorized()
    course = get_object_or_404(Course.objects.filter(owner=request.user), pk=pk)
    if request.method == 'GET':
        course = Course.objects.prefetch_related('assignments').get(pk=course.pk)
        return JsonResponse({
            'course': _course_payload(course, include_assignments=True),
            'semester': _semester_payload(course),
        })
    body = _json_body(request)
    if body is None:
        return JsonResponse({'detail': 'Invalid JSON.'}, status=400)
    form = CourseForm(body, instance=course)
    if not form.is_valid():
        return JsonResponse({'errors': _errors(form)}, status=400)
    return JsonResponse({'course': _course_payload(form.save())})


@require_POST
def course_assignments_view(request, pk):
    if not request.user.is_authenticated:
        return _unauthorized()
    course = get_object_or_404(Course.objects.filter(owner=request.user), pk=pk)
    body = _json_body(request)
    if body is None:
        return JsonResponse({'detail': 'Invalid JSON.'}, status=400)
    form = AssignmentForm(body)
    if not form.is_valid():
        return JsonResponse({'errors': _errors(form)}, status=400)
    assignment = form.save(commit=False)
    assignment.course = course
    assignment.save()
    return JsonResponse({'assignment': _assignment_payload(assignment)}, status=201)


@require_GET
def assignments_view(request):
    if not request.user.is_authenticated:
        return _unauthorized()
    assignments = Assignment.objects.owned_by(request.user).select_related('course')
    if request.GET.get('status') == Assignment.Status.COMPLETE:
        assignments = assignments.completed()
    elif request.GET.get('status') == Assignment.Status.INCOMPLETE:
        assignments = assignments.outstanding()
    return JsonResponse({'assignments': [_assignment_payload(item) for item in assignments]})


@require_http_methods(['GET', 'PUT', 'PATCH'])
def assignment_view(request, pk):
    if not request.user.is_authenticated:
        return _unauthorized()
    assignment = get_object_or_404(
        Assignment.objects.owned_by(request.user).select_related('course'), pk=pk,
    )
    if request.method == 'GET':
        return JsonResponse({'assignment': _assignment_payload(assignment)})
    body = _json_body(request)
    if body is None:
        return JsonResponse({'detail': 'Invalid JSON.'}, status=400)
    if request.method == 'PATCH':
        status = body.get('status')
        if status == Assignment.Status.COMPLETE:
            assignment.mark_complete()
        elif status == Assignment.Status.INCOMPLETE:
            assignment.reopen()
        else:
            return JsonResponse({'errors': {'status': ['Choose a valid status.']}}, status=400)
        assignment.refresh_from_db()
        return JsonResponse({'assignment': _assignment_payload(assignment)})
    form = AssignmentForm(body, instance=assignment)
    if not form.is_valid():
        return JsonResponse({'errors': _errors(form)}, status=400)
    return JsonResponse({'assignment': _assignment_payload(form.save())})
