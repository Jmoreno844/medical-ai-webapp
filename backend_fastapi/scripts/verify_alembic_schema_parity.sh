#!/usr/bin/env bash
# Compare PostgreSQL schema (subset of clinical + auth + fastapi_revoked_token)
# between a reference database and an Alembic-only database.
# The reference must include the same tables: if you only ran `manage.py migrate`
# on the reference, add the FastAPI token table (e.g. from a `pg_dump -t` of
# that table from an Alembic-provisioned DB) so the dump includes it.
# Requires: pg_dump, diff, same major PostgreSQL as production.
# Usage:
#   export PGPASSWORD=...
#   ALEMBIC_REF_DJANGO_DB=alembic_baseline_ref ALEMBIC_CANDIDATE_DB=alembic_apply_test \
#     ./backend_fastapi/scripts/verify_alembic_schema_parity.sh
set -euo pipefail

: "${PGHOST:=127.0.0.1}"
: "${PGPORT:=5433}"
: "${PGUSER:=${DB_USER:-juan}}"
: "${ALEMBIC_REF_DJANGO_DB:=alembic_baseline_ref}"
: "${ALEMBIC_CANDIDATE_DB:=alembic_apply_test}"

OUT="${TMPDIR:-/tmp}/alembic_parity_$$"
mkdir -p "$OUT"

args=(
  --schema-only --no-owner --no-privileges
  -h "$PGHOST" -p "$PGPORT" -U "$PGUSER"
)

tables=(
  django_content_type
  auth_group
  auth_group_permissions
  auth_permission
  users_user
  users_user_groups
  users_user_user_permissions
  patients_patient
  patients_patientdoctor
  encounters_encounter
  templates_basetemplate
  templates_doctortemplate
  templates_templateusage
  documents_document
  copilot_copilotrun
  copilot_copilotpatch
  copilot_copilotpatchset
  fastapi_revoked_token
)
for t in "${tables[@]}"; do
  args+=(-t "public.$t")
done

echo "==> dump reference (Django): $ALEMBIC_REF_DJANGO_DB"
pg_dump "${args[@]}" -d "$ALEMBIC_REF_DJANGO_DB" | sed -E '/^\\(un)?restrict /d' > "$OUT/django.sql"

echo "==> dump candidate (Alembic): $ALEMBIC_CANDIDATE_DB"
pg_dump "${args[@]}" -d "$ALEMBIC_CANDIDATE_DB" | sed -E '/^\\(un)?restrict /d' > "$OUT/alembic.sql"

# Ignore pg_dump / server version comment noise for CI drift.
norm() {
  sed -E \
    -e '/^-- Dumped from/d' \
    -e '/^-- Dumped by/d' \
    -e '/^SELECT pg_catalog\.set_config/d' \
    "$1"
}
norm "$OUT/django.sql" > "$OUT/django.norm.sql"
norm "$OUT/alembic.sql" > "$OUT/alembic.norm.sql"

if diff -u "$OUT/django.norm.sql" "$OUT/alembic.norm.sql"; then
  echo "==> schema parity: OK (subset matches)"
  rm -rf "$OUT"
  exit 0
else
  echo "==> schema parity: MISMATCH" >&2
  exit 1
fi
