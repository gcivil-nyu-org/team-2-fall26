# SemesterPilot

[![CI](https://github.com/gcivil-nyu-org/team-2-fall26/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/gcivil-nyu-org/team-2-fall26/actions/workflows/ci.yml)

A React and Django web app for NYU students to track courses, assignments, and deadlines in one place.

## Tech stack

- React / Vite frontend
- Python / Django JSON API
- SQLite for local dev, Postgres-ready for production (see Database below)
- AWS for hosting
- GitHub + ZenHub for source control and sprint tracking

## Setup

```bash
git clone https://github.com/gcivil-nyu-org/team-2-fall26.git
cd team-2-fall26
python3 -m venv venv
source venv/bin/activate        # venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
cd frontend
npm install
npm run build
cd ..
python manage.py runserver
```

Visit `http://localhost:8000/` to open the React app.

For frontend development with hot reloading, run Django on port 8000 and then
run `npm run dev` inside `frontend/`. Open `http://127.0.0.1:5173/app/`; Vite
proxies API calls to Django.

Deadline entry and display use Eastern time, regardless of the browser's local
zone. Saved deadlines keep their original due instant.

## Running tests

```bash
python manage.py test
```

Run `npm test` inside `frontend/` for the deadline time-zone and Vite base-path
regression tests, plus study-calendar helpers. Django shell tests use plain static storage so a fresh checkout
does not need a collected manifest; deployments still use WhiteNoise's hashed
assets after `collectstatic`.

GitHub Actions (`.github/workflows/ci.yml`) runs these on every push and pull
request to `develop` and `main`: `makemigrations --check`, the Django tests,
`npm test`, and `npm run build`. Results are in the repo's Actions tab.

## Study availability and calendar (#38, #39)

The React sidebar links to **Availability** (`/app/availability`) and **Study
calendar** (`/app/calendar`). Availability repeats Monday–Sunday and supports
multiple non-overlapping blocks per day. Availability and the calendar use New
York time. The availability migration converts legacy UTC blocks using Eastern
standard time (UTC−05:00), splitting blocks that cross midnight. After migration,
blocks repeat at the same New York wall-clock time through daylight-saving changes.
Saving an empty week clears availability;
the UI explains that availability is required before schedule generation.
Changing availability leaves already scheduled sessions unchanged.

Study sessions belong to an assignment, which supplies their course, task, and
account ownership. The calendar shows sessions overlapping the selected week,
including sessions crossing midnight, with previous/next/this-week navigation.
`?week=YYYY-MM-DD` selects the Monday–Sunday week containing that date.

API endpoints (session authentication and CSRF protection apply):

- `GET /api/study/availability/`: saved blocks and configuration state.
- `PUT /api/study/availability/`: atomically replace the user's weekly blocks;
  body: `{"blocks": [{"weekday": 0, "start_time": "09:00", "end_time": "11:00"}]}`.
  Weekdays run from Monday (0) to Sunday (6). Invalid or overlapping blocks
  return field errors without replacing saved availability.
- `GET /api/study/calendar/?week=2026-10-19`: the user's sessions for that week.

Run `python manage.py migrate` to create the study tables. Sessions can be
entered through Django admin while the separate automatic-generation story
(#41) is pending. No generated or example sessions are added by migrations.
Locking, rescheduling, completion, and deletion remain separate stories.

## Friends (#16, #17, #18)

The React sidebar links to **Friends** (`/app/friends`). Add a classmate by
their NYU email to send a friend request; they see it under "Friend requests"
and can accept or decline. You can cancel a request you sent while it's still
pending. If you send a request to someone who already sent you one, the two
requests are reconciled automatically and you become friends immediately,
instead of ending up with two pending requests waiting on each other.

A friend request can't be sent to yourself, to an email with no SemesterPilot
account, to someone you're already friends with, or a second time while an
earlier request between the same two people is still pending. A declined
request doesn't block trying again later.

Every person shown on the Friends page — a request's sender/recipient, or a
friend — shows their profile photo (see "Profile pictures" below) when
they've set one, falling back to an initial the same way the sidebar does.

API endpoints (session authentication and CSRF protection apply):

- `GET /api/social/friends/`: current friends, plus pending requests split
  into `received_requests` and `sent_requests`. Each person's record includes
  `profile_picture` (a URL, or `null` if they haven't set one).
- `POST /api/social/friends/requests/`: send a request; body:
  `{"email": "friend@nyu.edu"}`. Returns the new pending request (201), or the
  now-accepted request (200) if this reconciled a request already sent the
  other way.
- `PATCH /api/social/friends/requests/<id>/`: the recipient accepts or
  declines; body: `{"status": "accepted"}` or `{"status": "declined"}`.
- `DELETE /api/social/friends/requests/<id>/`: cancel or remove, depending on
  the request's status. Pending: only the original sender can cancel it.
  Accepted: either person in the friendship can remove it — see "Removing a
  friend" below. Already-declined requests can't be deleted this way (400).

Run `python manage.py migrate` to create the friend request table. Blocking
and messaging remain separate stories.

## Removing a friend (#19)

Each entry in "Your friends" has a **Remove** button; it asks you to confirm
before anything happens. Either person in the friendship can remove it, not
just whoever originally sent the request. Removing a friend doesn't delete
either account — there's no message history or other data tied to the
friendship to lose.

Under the hood this reuses the same `FriendRequest` row and the same
`DELETE /api/social/friends/requests/<id>/` endpoint as cancelling a pending
request (see "Friends (#16)" above): deleting an **accepted** request is
what "removing a friend" means, since the accepted row is the friendship
record itself. After removal, both people are free to send a new friend
request to each other.

## Viewing a friend's profile (#18)

Clicking a friend's name or photo in "Your friends" opens their profile —
their name, email, and photo (falling back to an initial, same as
everywhere else). The link lives at `/friends/<friendshipId>`, keyed by the
friendship itself rather than the other person's user id, so it only ever
resolves for an actual, current friendship.

`GET /api/social/friends/<friendshipId>/` backs this: it 404s for anyone who
isn't one of the two people in that friendship, for a friendship that's
still pending or was declined, and for one that's since been removed — the
same privacy pattern used elsewhere in this app, and the same error page a
stale or broken link produces.

**Note on #16/#17/#18's "search or identify by username" acceptance
criteria**: this app has no username concept a person ever sets or sees —
`User.username` is only Django's internal field, silently mirrored to each
person's email at signup. Searching or displaying "by username" isn't
buildable as those stories are worded unless the team adds real,
user-chosen usernames as their own feature first; in the meantime, name and
email are the only real identifiers these stories can use.

## Importing an Albert class schedule

Download the Class Calendar (.ics) from Albert and use **Import from Albert**
on the dashboard to review course matches and add class meetings to the study
calendar. If Albert abbreviates a course name, choose its existing course or
add a new one. Upload a fresh full-term export to refresh imported meetings.
Existing courses, coursework, availability, and study sessions are preserved.

## Assignment deadlines

Assignments require a title and deadline date and time; descriptions are optional.
Deadlines are entered and displayed in Eastern time, as labeled on the form and assignment
lists. Past deadlines are accepted. New assignments start as Incomplete.

Run `python manage.py migrate` after updating to apply the assignment schema changes.
Existing deadlines retain their stored instant; existing assignments
without a deadline remain readable. New submissions must include a deadline.

## Account deactivation and deletion (#36)

Open **Account settings** from the sidebar (`/app/settings/account`). Both
actions require the current password and a typed confirmation. Cancel clears
the confirmation form without sending a request.

- **Deactivate:** type `DEACTIVATE`. The account is disabled and signed out;
  courses, assignments, exams, availability, and study sessions are retained. An administrator must enable
  the user's **Active** flag in Django admin before they can sign in again.
  The password stays the same, but old sessions and reset links are invalidated.
- **Delete:** type `DELETE`. The account and its courses, assignments, exams,
  availability, and study sessions are permanently removed. Other students'
  accounts, coursework, and study data are unaffected.

Session-authenticated API endpoints are `POST /api/account/deactivate/` and
`DELETE /api/account/`. Both require CSRF protection and a JSON body with
`current_password` and `confirmation`. They always operate on the signed-in
account; request data cannot select another user. No database migration is
needed: deactivation uses Django's existing `is_active` flag.

## Database

Defaults to SQLite, no setup required. To use Postgres instead (e.g. for AWS RDS), set these in `.env`:

```
DATABASE_ENGINE=postgresql
DATABASE_NAME=...
DATABASE_USER=...
DATABASE_PASSWORD=...
DATABASE_HOST=...
DATABASE_PORT=5432
```

## Password reset

Signup is restricted to `@nyu.edu` email addresses. Students can reset a forgotten
password from the login page ("Forgot your password?"); the reset link expires
after 3 days and can only be used once.

By default, reset emails print to the `runserver` console instead of actually
sending (no setup needed for local dev). To send real emails, set these in `.env`:

```
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=noreply@semesterpilot.app
```

## Profile pictures

Students can upload a profile picture from `/profile` (JPG, PNG, or GIF, max 2MB,
enforced by `MAX_PROFILE_PICTURE_SIZE` in `config/settings.py`).

**Local dev (and the test suite): unchanged, local disk.** With no
`AWS_STORAGE_BUCKET_NAME` env var set, files are stored under `MEDIA_ROOT`
(`media/`, gitignored) and served from `MEDIA_URL` (`/media/`) by Django's dev
server when `DEBUG=True`. This is also what the test suite uses — nothing about
testing or local dev changes with the S3 support described below.

**Staging/prod: S3-ready, but still needs real infrastructure set up.**
Use the [private S3 deployment checklist](docs/s3-media-deployment.md) to configure buckets, EB instance-role IAM permissions, and acceptance tests. Keep the bucket private: the S3-backed storage emits time-limited signed URLs rather than publicly readable object URLs.
Elastic Beanstalk's app servers have ephemeral, non-shared local disks, so local
storage would lose every uploaded picture on the next deploy, or not show it on
a different instance behind the load balancer. The app code now supports S3 via
`django-storages` — setting `AWS_STORAGE_BUCKET_NAME` (plus optionally
`AWS_S3_REGION_NAME`, default `us-east-1`) in `config/settings.py` switches
`STORAGES['default']` to S3 automatically, no code change needed. AWS
credentials are deliberately **not** read from Django settings: boto3 resolves
them itself and will prefer an IAM instance role attached to the EB environment
over any access-key env vars, so no secret keys need to be stored in EB's
environment config at all.

What *isn't* done, and can't be from code alone: an actual S3 bucket and IAM
role/policy need to exist in AWS, and `AWS_STORAGE_BUCKET_NAME` (and the IAM
role, or `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`) need to be set on the real
EB environment. Flagging this the same way the SMTP setup was flagged for
password reset: it's an infrastructure/ops task for whoever manages the EB
environments and AWS account, not something this app's code alone can finish.

**Also fixed:** EB's default nginx config caps uploads at 1MB, below our 2MB
app-level limit, which would reject a valid upload before it even reached
Django. `.ebextensions/02_nginx_upload_size.config` raises nginx's own limit to
3MB so the app's own size-limit error (not a generic nginx 413) is what a user
sees for an oversized file.

## Project structure

Each feature lives in its own app under `apps/`, registered in `config/settings.py`:

```
apps/
  accounts/      # user model and signup validation
  api/           # session-authenticated JSON endpoints
  coursework/    # course and assignment domain logic
  study/         # availability and study-session scheduling
  social/        # friend requests and the friends list
config/          # project settings, root URLs
templates/       # minimal Django shell that mounts React
frontend/        # React single-page app
static/frontend/ # production bundle generated by Vite
```

The browser UI lives in `frontend/src`. Django serves the JSON API from
`apps/api` and hosts the production React bundle under `/app/`. Django forms
provide server-side validation for API writes; UI rendering stays in React.
The root URL opens the React application.

## Workflow

1. Branch off `develop`: `feature/<issue-number>-<short-name>`
2. Commit, push, open a PR into `develop`
3. Get it reviewed by a teammate before merging (per our Definition of Done)

## Deployment (AWS Elastic Beanstalk)

Two environments: `develop` → **staging**, `main` → **production**.

| Environment | Branch | EB environment name |
|---|---|---|
| Staging | `develop` | `semesterpilot-staging` |
| Production | `main` | `semesterpilot-prod` |

Config lives in `.ebextensions/01_django.config` (runs `migrate` and `collectstatic` on each deploy). Static files, including the committed React production bundle, are served by WhiteNoise. Run `npm run build` after frontend changes and commit the updated `static/frontend` output.

Each environment needs these environment properties (EB console → Configuration → Updates, monitoring, and logging → Environment properties):

```
DJANGO_SECRET_KEY=<long random string, different per environment>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=<env-url>.elasticbeanstalk.com
DJANGO_CSRF_TRUSTED_ORIGINS=http://<env-url>.elasticbeanstalk.com
DATABASE_ENGINE=postgresql
DATABASE_NAME=... DATABASE_USER=... DATABASE_PASSWORD=... DATABASE_HOST=... DATABASE_PORT=5432
```

With `DJANGO_DEBUG=False` the app refuses to start unless `DJANGO_SECRET_KEY` and all of the Postgres `DATABASE_*` vars are set, so a misconfigured environment fails the deploy instead of silently using SQLite. The RDS connection uses `sslmode=require` (override with `DATABASE_SSLMODE` for a local Postgres without SSL). HTTPS settings (SSL redirect, secure cookies, HSTS) are off until an environment has a certificate; then set `DJANGO_SECURE_HTTPS=True`.

Both environments are single-instance (`eb create --single`), so there's no load balancer health check hitting the instance IP. If we ever switch to a load-balanced environment, ALLOWED_HOSTS will need the instance's private IP or a health-check exemption.

Deploy:

```bash
pip install awsebcli
eb init                       # once: Python 3.13 (Amazon Linux 2023), region us-east-2 (Ohio; our account is limited to this region)
git checkout develop && eb deploy semesterpilot-staging
git checkout main    && eb deploy semesterpilot-prod
```


### Study session controls (#42, #43)

On the study calendar, **Lock** preserves a session's time during future schedule
regeneration; **Unlock** makes it replaceable again. Locked sessions have a badge
and a distinct border. **Reschedule** opens start/end fields in Eastern time. Saving
outside availability or over another session shows warnings first; **Move anyway**
confirms that specific move, while **Cancel** leaves it unchanged. Editing either
field clears the previous warning confirmation. A manual move keeps the lock state.

Run `python manage.py migrate` after pulling to add `StudySession.is_locked`.
`PATCH /api/study/sessions/<id>/` accepts `is_locked` or both `starts_at` and
`ends_at`, with `confirm_warnings: true` to override current scheduling warnings.
Only the signed-in owner's sessions can be changed; writes require CSRF protection.

**Integration with #41:** automatic generation is a separate, still-open story.
`apps.study.services.replace_unlocked_sessions(user, starts_at, ends_at, candidates)`
is the tested persistence boundary for that generator. Plan around existing locked
sessions and pass new, unsaved `StudySession` instances. The helper preserves locked
sessions and other accounts' sessions, replaces only unlocked sessions fully inside
the planning window, and rejects candidates that overlap preserved sessions or each
other. Session edits, availability updates, and this helper serialize writes using
the same account-row lock. Jane's generator must call this helper (or provide the
same guarantees); end-to-end generation integration remains to be checked in #41.


The generator can use `preserved_sessions(user, starts_at, ends_at)` from
`apps.study.services` to obtain the exact queryset of sessions the replacement
helper keeps: locked sessions, sessions crossing either window boundary, and
sessions outside the window. Both helpers share that selection, so planning and
replacement cannot drift. Hold `lock_study_account(user)` within one
`transaction.atomic()` block while reading preserved sessions, planning, and
calling `replace_unlocked_sessions` to serialize against availability/session edits.
