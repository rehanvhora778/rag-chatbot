#!/usr/bin/env bash
# Render runs this once per deploy, before starting the web service.
# `set -o errexit` makes the deploy fail loudly instead of starting a half-built app.
set -o errexit

pip install --upgrade pip
pip install -r requirements-prod.txt

# Django's admin/browsable-API assets, gathered for WhiteNoise to serve.
python manage.py collectstatic --no-input

# SQLite holds only Django's own auth/JWT tables (all project data is in MongoDB).
python manage.py migrate --no-input

# Seeds the admin account from DEFAULT_ADMIN_EMAIL / DEFAULT_ADMIN_PASSWORD.
# Safe to re-run: it updates the existing account rather than creating a second.
python manage.py create_admin
