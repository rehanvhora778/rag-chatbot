#!/usr/bin/env bash
# Render runs this once per deploy, before starting the web service.
# `set -o errexit` makes the deploy fail loudly instead of starting a half-built app.
set -o errexit

pip install --upgrade pip
pip install -r requirements-prod.txt

# Django's admin/browsable-API assets, gathered for WhiteNoise to serve.
python manage.py collectstatic --no-input

# Applies Django's own auth/JWT tables, and — once DATABASE_URL points at
# PostgreSQL — the project's domain models as well.
python manage.py migrate --no-input

# Seeds the admin account from DEFAULT_ADMIN_EMAIL / DEFAULT_ADMIN_PASSWORD.
# Safe to re-run: it updates the existing account rather than creating a second.
#
# --skip-if-unset so a deploy that has no admin password configured logs a
# warning and carries on, rather than failing the build. There is no default
# password any more: a seed credential in the repository is a credential in
# every clone of it.
python manage.py create_admin --skip-if-unset
