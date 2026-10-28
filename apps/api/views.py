import json
import logging
from datetime import timedelta

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.forms import ProfileForm, ProfilePictureForm, SignUpForm
from apps.accounts.models import User
from apps.coursework.forms import AssignmentForm, CourseForm, ExamForm
from apps.coursework.models import Assignment, Course, Exam

logger = logging.getLogger(__name__)


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
    return {
        'id': user.pk,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'profile_picture': user.profile_picture.url if user.profile_picture else None,
    }


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
        data['exams'] = [_exam_payload(item) for item in course.exams.all()]
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


def _exam_payload(exam):
    return {
        'id': exam.pk,
        'kind': 'exam',
        'title': exam.title,
        'starts_at': timezone.localtime(exam.starts_at).isoformat(),
        'location': exam.location,
        'course': {
            'id': exam.course_id,
            'name': exam.course.name,
            'code': exam.course.code,
        },
    }


def _upcoming_payload(assignments, exams):
    # One outstanding-work list: soonest first, so overdue assignments lead and
    # undated assignments trail, with exams slotted in by their start time.
    items = [(item.due_date, item.title, {**_assignment_payload(item), 'kind': 'assignment'}) for item in assignments]
    items += [(item.starts_at, item.title, _exam_payload(item)) for item in exams]
    items.sort(key=lambda item: (item[0] is None, item[0] or timezone.now(), item[1]))
    return [payload for _, _, payload in items]


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


@require_POST
def password_reset_request_view(request):
    body = _json_body(request)
    if body is None:
        return JsonResponse({'detail': 'Invalid JSON.'}, status=400)
    email = str(body.get('email', '')).strip().lower()
    user = User.objects.filter(email=email).first()
    if user is not None:
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_url = request.build_absolute_uri(f'/app/reset-password/{uid}/{token}')
        try:
            send_mail(
                subject='Reset your SemesterPilot password',
                message=(
                    f'Use this link to reset your password: {reset_url}\n\n'
                    'If you did not request this, you can ignore this email.'
                ),
                from_email=None,
                recipient_list=[user.email],
            )
        except Exception:
            # Don't let a broken mail server surface to the requester (that would
            # also leak whether the account exists) — but do log it, so a
            # misconfigured EMAIL_* setup in staging/prod shows up somewhere.
            logger.exception('Failed to send password reset email to %s', user.email)
    # Same response whether or not the account exists, so this endpoint never
    # reveals which emails have accounts.
    return JsonResponse({'ok': True})


@require_POST
def password_reset_confirm_view(request):
    body = _json_body(request)
    if body is None:
        return JsonResponse({'detail': 'Invalid JSON.'}, status=400)
    try:
        user = User.objects.get(pk=urlsafe_base64_decode(body.get('uid', '')).decode())
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    if user is None or not default_token_generator.check_token(user, body.get('token', '')):
        return JsonResponse({'detail': 'This reset link is invalid or has expired.'}, status=400)
    password = body.get('password', '')
    if password != body.get('password_confirm', ''):
        return JsonResponse({'errors': {'password_confirm': ['Passwords do not match.']}}, status=400)
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        return JsonResponse({'errors': {'password': list(exc.messages)}}, status=400)
    user.set_password(password)
    user.save()
    return JsonResponse({'ok': True})


@require_http_methods(['GET', 'PUT'])
def profile_view(request):
    if not request.user.is_authenticated:
        return _unauthorized()
    if request.method == 'GET':
        return JsonResponse({'user': _user_payload(request.user)})
    body = _json_body(request)
    if body is None:
        return JsonResponse({'detail': 'Invalid JSON.'}, status=400)
    form = ProfileForm(body, instance=request.user)
    if not form.is_valid():
        return JsonResponse({'errors': _errors(form)}, status=400)
    user = form.save()
    return JsonResponse({'user': _user_payload(user)})


@require_http_methods(['POST', 'DELETE'])
def profile_picture_view(request):
    if not request.user.is_authenticated:
        return _unauthorized()
    old_picture = request.user.profile_picture
    if request.method == 'DELETE':
        if old_picture:
            old_picture.delete(save=False)
        request.user.profile_picture = None
        request.user.save()
        return JsonResponse({'user': _user_payload(request.user)})
    form = ProfilePictureForm(request.POST, request.FILES, instance=request.user)
    if not form.is_valid():
        return JsonResponse({'errors': _errors(form)}, status=400)
    form.save()
    if old_picture:
        # Clean up the previous file now that the new one is safely saved
        # under its own (storage-assigned) name.
        old_picture.delete(save=False)
    return JsonResponse({'user': _user_payload(request.user)})


@require_POST
def change_password_view(request):
    if not request.user.is_authenticated:
        return _unauthorized()
    body = _json_body(request)
    if body is None:
        return JsonResponse({'detail': 'Invalid JSON.'}, status=400)
    current_password = body.get('current_password', '')
    new_password = body.get('new_password', '')
    new_password_confirm = body.get('new_password_confirm', '')
    if not request.user.check_password(current_password):
        return JsonResponse({'errors': {'current_password': ['Current password is incorrect.']}}, status=400)
    if new_password != new_password_confirm:
        return JsonResponse({'errors': {'new_password_confirm': ['Passwords do not match.']}}, status=400)
    try:
        validate_password(new_password, user=request.user)
    except DjangoValidationError as exc:
        return JsonResponse({'errors': {'new_password': list(exc.messages)}}, status=400)
    request.user.set_password(new_password)
    request.user.save()
    # Keep the current session valid across the password change, instead of
    # forcing an immediate re-login (Django invalidates the session hash on
    # password change by default).
    update_session_auth_hash(request, request.user)
    return JsonResponse({'ok': True})


@require_GET
def dashboard_view(request):
    if not request.user.is_authenticated:
        return _unauthorized()
    now = timezone.now()
    week_end = now + timedelta(days=7)
    assignments = Assignment.objects.owned_by(request.user)
    outstanding = assignments.outstanding().select_related('course')
    exams = Exam.objects.owned_by(request.user).upcoming().select_related('course')
    courses = request.user.courses.annotate(assignment_count=Count('assignments'))
    return JsonResponse({
        'user': _user_payload(request.user),
        'metrics': {
            'courses': courses.count(),
            'due_this_week': (
                outstanding.filter(due_date__gte=now, due_date__lte=week_end).count()
                + exams.filter(starts_at__lte=week_end).count()
            ),
            'overdue': assignments.overdue().count(),
        },
        'courses': [_course_payload(course) for course in courses],
        'assignments': [_assignment_payload(item) for item in outstanding],
        'upcoming': _upcoming_payload(outstanding, exams),
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


@require_http_methods(['GET', 'PUT', 'DELETE'])
def course_view(request, pk):
    if not request.user.is_authenticated:
        return _unauthorized()
    course = get_object_or_404(Course.objects.filter(owner=request.user), pk=pk)
    if request.method == 'DELETE':
        course.delete()
        return JsonResponse({'ok': True})
    if request.method == 'GET':
        course = Course.objects.prefetch_related('assignments', 'exams').get(pk=course.pk)
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


@require_POST
def course_exams_view(request, pk):
    if not request.user.is_authenticated:
        return _unauthorized()
    course = get_object_or_404(Course.objects.filter(owner=request.user), pk=pk)
    body = _json_body(request)
    if body is None:
        return JsonResponse({'detail': 'Invalid JSON.'}, status=400)
    form = ExamForm(body)
    if not form.is_valid():
        return JsonResponse({'errors': _errors(form)}, status=400)
    exam = form.save(commit=False)
    exam.course = course
    exam.save()
    return JsonResponse({'exam': _exam_payload(exam)}, status=201)


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


@require_http_methods(['GET', 'PUT', 'PATCH', 'DELETE'])
def assignment_view(request, pk):
    if not request.user.is_authenticated:
        return _unauthorized()
    assignment = get_object_or_404(
        Assignment.objects.owned_by(request.user).select_related('course'), pk=pk,
    )
    if request.method == 'GET':
        return JsonResponse({'assignment': _assignment_payload(assignment)})
    if request.method == 'DELETE':
        assignment.delete()
        return JsonResponse({'ok': True})
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
