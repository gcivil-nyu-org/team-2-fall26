from django.contrib.auth.models import Group, Permission
from django.db.models import Q
from django.db import transaction

# #60: who can use the admin site, and who decides that.
#
# Two levels of administrator:
#   - Super administrators (is_superuser) can do everything, including granting
#     and revoking administrator access. The first one is created with
#     `python manage.py createsuperuser`; they are never changed from the admin.
#   - Administrators (is_staff, in the "Administrators" group) can sign in to
#     the admin, manage student accounts (#54) and view reported content
#     (#67). Nothing else: they cannot see other administrators or change who
#     has access.
ADMIN_GROUP_NAME = 'Administrators'
ADMIN_PERMISSIONS = ('view_user', 'change_user', 'delete_user')
# #67: the reported-content queue. Reviewing reports is #56.
REPORT_PERMISSIONS = ('view_contentreport',)


def can_manage_administrators(user):
    # The "authorized user" check: only an active super administrator decides
    # who else gets administrator access.
    return bool(user.is_active and user.is_superuser)


def access_level(user):
    if user.is_superuser:
        return 'Super administrator'
    if user.is_staff:
        return 'Administrator'
    return 'Student'


def administrator_group():
    # Created on first use and re-synced every time, so the group always holds
    # exactly the student-account and report permissions and never drifts.
    group, _ = Group.objects.get_or_create(name=ADMIN_GROUP_NAME)
    permissions = Permission.objects.filter(
        Q(content_type__app_label='accounts', content_type__model='user', codename__in=ADMIN_PERMISSIONS)
        | Q(content_type__app_label='social', content_type__model='contentreport', codename__in=REPORT_PERMISSIONS),
    )
    group.permissions.set(permissions)
    return group


def has_administrator_group(user):
    return user.groups.filter(name=ADMIN_GROUP_NAME).exists()


def grant_block_reason(request, user):
    # An account someone marked as staff by other means (the shell, say) has no
    # permissions until it joins the group, so granting finishes the job for it.
    if user.is_superuser or (user.is_staff and has_administrator_group(user)):
        return 'already has administrator access'
    if not user.is_active:
        return 'the account is deactivated, so reactivate it first'
    return None


def revoke_block_reason(request, user):
    if user.pk == request.user.pk:
        return 'you cannot do this to your own account'
    if user.is_superuser:
        return 'super administrators are managed outside the admin site'
    return None


@transaction.atomic
def grant_administrator_access(user):
    user.is_staff = True
    user.save(update_fields=['is_staff'])
    user.groups.add(administrator_group())


@transaction.atomic
def revoke_administrator_access(user):
    # Admin pages check is_staff on every request, so this takes effect on the
    # person's very next click even if they are signed in right now.
    user.is_staff = False
    user.save(update_fields=['is_staff'])
    user.groups.remove(administrator_group())
