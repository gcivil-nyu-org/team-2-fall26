from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


def send_admin_password_reset_email(user, request):
    # Same link and token as the student-facing "Forgot your password?" flow
    # (apps/api/views.py), so the student sets their own password. An
    # administrator never sees or chooses it. Raises if the mail can't be sent.
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    reset_url = request.build_absolute_uri(f'/app/reset-password/{uid}/{token}')
    send_mail(
        subject='Reset your SemesterPilot password',
        message=(
            'A SemesterPilot administrator sent you this link to reset your password.\n\n'
            f'Use this link to reset your password: {reset_url}\n\n'
            'If you were not expecting this, you can ignore this email.'
        ),
        from_email=None,
        recipient_list=[user.email],
    )
