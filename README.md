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

## Assignment deadlines

Assignments require a title and deadline date and time; descriptions are optional.
Deadlines are entered and displayed in UTC, as labeled on the form and assignment
lists. Past deadlines are accepted. New assignments start as Incomplete.

Run `python manage.py migrate` after updating to apply the assignment schema changes.
Existing dated assignments retain their date at midnight UTC; existing assignments
without a deadline remain readable. New submissions must include a deadline.

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
