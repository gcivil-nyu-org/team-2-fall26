import logging
from datetime import timedelta

from django import forms
from django.contrib import admin, messages
from django.db.models import Count, Q
from django.utils import timezone

from .forms import validate_student_email
from .models import User
from .password_reset import send_admin_password_reset_email

logger = logging.getLogger(__name__)

admin.site.site_header = 'SemesterPilot administration'
admin.site.site_title = 'SemesterPilot admin'
admin.site.index_title = 'Manage SemesterPilot'


def protection_reason(request, user):
    # An administrator can't deactivate or delete the account they are signed
    # in with, so they can't lock themselves out. Only active superusers can
    # reach other administrators' accounts at all, so at least one active
    # administrator always remains.
    if user.pk == request.user.pk:
        return 'you cannot do this to your own account'
    return None


class RoleFilter(admin.SimpleListFilter):
    title = 'role'
    parameter_name = 'role'

    def lookups(self, request, model_admin):
        return [('student', 'Students'), ('admin', 'Administrators')]

    def queryset(self, request, queryset):
        if self.value() == 'student':
            return queryset.filter(is_staff=False, is_superuser=False)
        if self.value() == 'admin':
            return queryset.filter(Q(is_staff=True) | Q(is_superuser=True))
        return queryset


class SignInFilter(admin.SimpleListFilter):
    title = 'last sign-in'
    parameter_name = 'signin'

    def lookups(self, request, model_admin):
        return [('never', 'Never signed in'), ('recent', 'Within 30 days'), ('stale', 'Over 30 days ago')]

    def queryset(self, request, queryset):
        cutoff = timezone.now() - timedelta(days=30)
        if self.value() == 'never':
            return queryset.filter(last_login__isnull=True)
        if self.value() == 'recent':
            return queryset.filter(last_login__gte=cutoff)
        if self.value() == 'stale':
            return queryset.filter(last_login__lt=cutoff)
        return queryset


class StudentAccountForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'bio', 'is_active')

    def clean_email(self):
        return validate_student_email(self.cleaned_data['email'], exclude_pk=self.instance.pk)


@admin.register(User)
class StudentAccountAdmin(admin.ModelAdmin):
    form = StudentAccountForm
    list_display = ('email', 'full_name', 'role', 'status', 'courses', 'date_joined', 'last_login')
    list_filter = ('is_active', RoleFilter, SignInFilter, ('date_joined', admin.DateFieldListFilter))
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('-date_joined',)
    list_per_page = 50
    actions = ['deactivate_accounts', 'reactivate_accounts', 'send_password_reset', 'delete_selected']
    fieldsets = (
        ('Account', {
            'fields': ('email', 'is_active'),
            'description': 'Deactivating blocks sign-in but keeps all of the student’s data. '
                           'Students set their own passwords, so use “Send password reset email” instead of changing one here.',
        }),
        ('Profile', {'fields': ('first_name', 'last_name', 'bio')}),
        ('Activity', {'fields': ('role', 'courses', 'date_joined', 'last_login')}),
    )
    readonly_fields = ('role', 'courses', 'date_joined', 'last_login')

    # Students sign themselves up, so there is nothing to create here.
    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        queryset = super().get_queryset(request).annotate(course_count=Count('courses', distinct=True))
        if not request.user.is_superuser:
            # Staff who aren't superusers manage students only.
            queryset = queryset.filter(is_staff=False, is_superuser=False)
        return queryset

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None and protection_reason(request, obj):
            readonly.append('is_active')
        return readonly

    def has_delete_permission(self, request, obj=None):
        allowed = super().has_delete_permission(request, obj)
        if allowed and obj is not None:
            return protection_reason(request, obj) is None
        return allowed

    def save_model(self, request, obj, form, change):
        # Sign-in looks accounts up by username, which this app keeps equal to
        # the email for students, so a corrected email has to carry the
        # username with it. An account whose username was chosen separately
        # (an administrator made with createsuperuser) keeps it.
        if change and 'email' in form.changed_data and obj.username == form.initial.get('email'):
            obj.username = obj.email
        super().save_model(request, obj, form, change)

    @admin.display(description='Name', ordering='first_name')
    def full_name(self, obj):
        return ' '.join(filter(None, [obj.first_name, obj.last_name])) or '—'

    @admin.display(description='Role', ordering='is_staff')
    def role(self, obj):
        return 'Administrator' if obj.is_staff or obj.is_superuser else 'Student'

    @admin.display(description='Status', ordering='is_active')
    def status(self, obj):
        return 'Active' if obj.is_active else 'Deactivated'

    @admin.display(description='Courses', ordering='course_count')
    def courses(self, obj):
        count = getattr(obj, 'course_count', None)
        return obj.courses.count() if count is None else count

    def _report(self, request, done, skipped, verb):
        if done:
            self.message_user(request, f'{verb} {done} account{"s" if done != 1 else ""}.', messages.SUCCESS)
        for user, reason in skipped:
            self.message_user(request, f'Skipped {user.email}: {reason}.', messages.WARNING)
        if not done and not skipped:
            self.message_user(request, 'Nothing to do for the selected accounts.', messages.INFO)

    @admin.action(description='Deactivate selected accounts', permissions=['change'])
    def deactivate_accounts(self, request, queryset):
        done, skipped = 0, []
        for user in queryset:
            if not user.is_active:
                continue
            reason = protection_reason(request, user)
            if reason:
                skipped.append((user, reason))
                continue
            user.is_active = False
            user.save(update_fields=['is_active'])
            self.log_change(request, user, 'Deactivated account.')
            done += 1
        self._report(request, done, skipped, 'Deactivated')

    @admin.action(description='Reactivate selected accounts', permissions=['change'])
    def reactivate_accounts(self, request, queryset):
        done = 0
        for user in queryset:
            if user.is_active:
                continue
            user.is_active = True
            user.save(update_fields=['is_active'])
            self.log_change(request, user, 'Reactivated account.')
            done += 1
        self._report(request, done, [], 'Reactivated')

    @admin.action(description='Send password reset email', permissions=['change'])
    def send_password_reset(self, request, queryset):
        done, skipped = 0, []
        for user in queryset:
            if not user.is_active:
                skipped.append((user, 'the account is deactivated, so reactivate it first'))
                continue
            try:
                send_admin_password_reset_email(user, request)
            except Exception:
                logger.exception('Failed to send admin-initiated password reset email to %s', user.email)
                skipped.append((user, 'the email could not be sent'))
                continue
            self.log_change(request, user, 'Sent password reset email.')
            done += 1
        if done:
            self.message_user(request, f'Sent {done} password reset email{"s" if done != 1 else ""}.', messages.SUCCESS)
        for user, reason in skipped:
            self.message_user(request, f'Skipped {user.email}: {reason}.', messages.WARNING)
