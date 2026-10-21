# SemesterPilot

A Django web app for NYU students to track courses, assignments, and deadlines in one place.

## Tech stack

- Python / Django
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
python manage.py runserver
```

Visit `http://localhost:8000/accounts/signup/` to create an account.

## Running tests

```bash
python manage.py test
```

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

## Project structure

Each feature lives in its own app under `apps/`, registered in `config/settings.py`:

```
apps/
  accounts/      # login, signup, auth (#61)
  coursework/    # courses, assignments (#9)
config/          # project settings, root URLs
templates/       # shared + per-app templates
```

Add a new feature as a new app under `apps/` with its own `urls.py` (namespaced) and templates under `templates/<app_name>/`.

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

Config lives in `.ebextensions/01_django.config` (runs `migrate` and `collectstatic` on each deploy). Static files are served by WhiteNoise.

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
