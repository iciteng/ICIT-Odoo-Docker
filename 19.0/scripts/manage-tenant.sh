#!/usr/bin/env bash
set -euo pipefail

# Manage Odoo tenant databases in Docker.
# Assumes dbfilter=^%d$ (tenant subdomain maps to DB name).

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo "Error: docker compose (or docker-compose) is required." >&2
  exit 1
fi

DB_SERVICE="${DB_SERVICE:-db}"
WEB_SERVICE="${WEB_SERVICE:-web}"
POSTGRES_USER="${POSTGRES_USER:-odoo}"
BACKUP_DIR="${BACKUP_DIR:-backups}"

usage() {
  cat <<'EOF'
Usage:
  scripts/manage-tenant.sh create <tenant_db>
  scripts/manage-tenant.sh backup <tenant_db> [output.sql]
  scripts/manage-tenant.sh restore <tenant_db> <input.sql>
  scripts/manage-tenant.sh delete <tenant_db>
  scripts/manage-tenant.sh list

Commands:
  create   Create and initialize a new tenant database (base module only).
  backup   Export tenant database to a SQL dump file.
  restore  Drop/recreate tenant database and import SQL dump.
  delete   Drop tenant database after terminating active sessions.
  list     Show all non-template databases.

Notes:
  - Tenant DB names should match subdomains (dbfilter=^%d$).
  - Override DB service with DB_SERVICE env var (default: db).
  - Override web service with WEB_SERVICE env var (default: web).
  - Override backup dir with BACKUP_DIR env var (default: backups).
EOF
}

require_compose() {
  "${COMPOSE[@]}" ps >/dev/null
}

validate_db_name() {
  local db="$1"
  if [[ ! "$db" =~ ^[a-z0-9][a-z0-9_-]*$ ]]; then
    echo "Error: invalid tenant db name '${db}'." >&2
    echo "Use lowercase letters, numbers, underscore, or dash." >&2
    exit 1
  fi
}

terminate_connections() {
  local db="$1"
  "${COMPOSE[@]}" exec -T "${DB_SERVICE}" psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d postgres \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${db}' AND pid <> pg_backend_pid();" >/dev/null
}

create_tenant() {
  local db="$1"
  validate_db_name "${db}"
  require_compose
  "${COMPOSE[@]}" run --rm "${WEB_SERVICE}" \
    odoo -d "${db}" --without-demo=all -i base --stop-after-init
  echo "Tenant '${db}' created."
}

backup_tenant() {
  local db="$1"
  local output="${2:-${BACKUP_DIR}/${db}-$(date +%Y%m%d-%H%M%S).sql}"
  validate_db_name "${db}"
  require_compose
  mkdir -p "$(dirname "${output}")"
  "${COMPOSE[@]}" exec -T "${DB_SERVICE}" pg_dump -U "${POSTGRES_USER}" -d "${db}" --no-owner --no-privileges > "${output}"
  echo "Backup saved to ${output}"
}

restore_tenant() {
  local db="$1"
  local input="$2"
  validate_db_name "${db}"
  require_compose
  if [[ ! -f "${input}" ]]; then
    echo "Error: backup file not found: ${input}" >&2
    exit 1
  fi

  terminate_connections "${db}"
  "${COMPOSE[@]}" exec -T "${DB_SERVICE}" psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d postgres \
    -c "DROP DATABASE IF EXISTS \"${db}\";"
  "${COMPOSE[@]}" exec -T "${DB_SERVICE}" psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d postgres \
    -c "CREATE DATABASE \"${db}\";"
  "${COMPOSE[@]}" exec -T "${DB_SERVICE}" psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d "${db}" < "${input}"
  echo "Tenant '${db}' restored from ${input}"
}

delete_tenant() {
  local db="$1"
  validate_db_name "${db}"
  require_compose
  terminate_connections "${db}"
  "${COMPOSE[@]}" exec -T "${DB_SERVICE}" psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d postgres \
    -c "DROP DATABASE IF EXISTS \"${db}\";"
  echo "Tenant '${db}' deleted."
}

list_tenants() {
  require_compose
  "${COMPOSE[@]}" exec -T "${DB_SERVICE}" psql -U "${POSTGRES_USER}" -d postgres -At \
    -c "SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname;"
}

main() {
  local cmd="${1:-}"
  case "${cmd}" in
    create)
      [[ $# -eq 2 ]] || { usage; exit 1; }
      create_tenant "$2"
      ;;
    backup)
      [[ $# -ge 2 && $# -le 3 ]] || { usage; exit 1; }
      backup_tenant "$2" "${3:-}"
      ;;
    restore)
      [[ $# -eq 3 ]] || { usage; exit 1; }
      restore_tenant "$2" "$3"
      ;;
    delete)
      [[ $# -eq 2 ]] || { usage; exit 1; }
      delete_tenant "$2"
      ;;
    list)
      [[ $# -eq 1 ]] || { usage; exit 1; }
      list_tenants
      ;;
    -h|--help|help|"")
      usage
      ;;
    *)
      echo "Error: unknown command '${cmd}'" >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"
