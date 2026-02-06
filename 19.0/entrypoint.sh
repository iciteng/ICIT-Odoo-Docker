#!/bin/bash
set -e

# =============================================================================
# Odoo entrypoint with DO Spaces/S3 and SSL support
# =============================================================================

if [ -v PASSWORD_FILE ]; then
    PASSWORD="$(< $PASSWORD_FILE)"
fi

# Database connection defaults
: ${HOST:=${DB_PORT_5432_TCP_ADDR:='db'}}
: ${DB_PORT:=${DB_PORT_5432_TCP_PORT:=5432}}
: ${USER:=${DB_ENV_POSTGRES_USER:=${POSTGRES_USER:='odoo'}}}
: ${PASSWORD:=${DB_ENV_POSTGRES_PASSWORD:=${POSTGRES_PASSWORD:='odoo'}}}

# Export PGSSLMODE for libpq (used by psycopg2).
# This is the correct way to configure SSL — Odoo does not accept
# --db_sslmode as a CLI argument.
if [ -n "${DB_SSLMODE}" ]; then
    export PGSSLMODE="${DB_SSLMODE}"
fi

# -----------------------------------------------------------------------------
# Append runtime settings directly to the main config file.
# The container filesystem is ephemeral, so mutating the file is safe.
# This avoids the --config flag which REPLACES the config rather than merging.
# -----------------------------------------------------------------------------
ODOO_CONF="/etc/odoo/odoo.conf"

# Admin password from environment
if [ -n "${ODOO_ADMIN_PASSWD}" ]; then
    echo "" >> "${ODOO_CONF}"
    echo "admin_passwd = ${ODOO_ADMIN_PASSWD}" >> "${ODOO_CONF}"
fi

# DB SSL mode in config (supplements PGSSLMODE env var)
if [ -n "${DB_SSLMODE}" ] && ! grep -q "^db_sslmode" "${ODOO_CONF}"; then
    echo "db_sslmode = ${DB_SSLMODE}" >> "${ODOO_CONF}"
fi

# ---------------------------------------------------------------------------
# Attachment storage strategy
# ---------------------------------------------------------------------------
# Stock Odoo only supports ir_attachment.location = "file" (default) or "db".
# S3/Spaces requires an OCA addon (e.g. base_attachment_object_storage from
# https://github.com/OCA/storage or attachment_s3 from
# https://github.com/camptocamp/odoo-cloud-platform).
#
# When SPACES_* env vars are set AND the addon is installed, the S3 config
# is injected below. Otherwise, on ephemeral filesystems (App Platform),
# we fall back to "db" so attachments survive container restarts.
# ---------------------------------------------------------------------------
if [ -n "${SPACES_BUCKET}" ] && [ -n "${SPACES_ENDPOINT}" ]; then
    # Check if the OCA S3 addon is actually installed in addons_path
    S3_ADDON_FOUND=false
    for d in /mnt/extra-addons/base_attachment_object_storage \
             /mnt/extra-addons/attachment_s3 \
             /mnt/extra-addons/fs_storage; do
        if [ -d "$d" ]; then
            S3_ADDON_FOUND=true
            break
        fi
    done

    if [ "$S3_ADDON_FOUND" = true ]; then
        cat >> "${ODOO_CONF}" <<EOF

; S3/Spaces attachment storage (injected at runtime)
ir_attachment.location = s3

[fs_storage]
spaces.protocol = s3
spaces.options = {"endpoint_url": "${SPACES_ENDPOINT}", "key": "${SPACES_ACCESS_KEY}", "secret": "${SPACES_SECRET_KEY}"}
spaces.bucket_name = ${SPACES_BUCKET}
spaces.directory_path = ${SPACES_PREFIX:-odoo}
spaces.optimizes_directory_path = True

[fs_attachment]
fallback_to_db_store = False
autovacuum_gc = True
EOF
        echo "entrypoint: S3 attachment storage enabled (bucket: ${SPACES_BUCKET})"
    else
        echo "WARNING: SPACES_* env vars are set but no S3 addon found in /mnt/extra-addons." >&2
        echo "WARNING: Install OCA base_attachment_object_storage or camptocamp attachment_s3." >&2
        echo "WARNING: Falling back to ir_attachment.location = db" >&2
        echo "" >> "${ODOO_CONF}"
        echo "ir_attachment.location = db" >> "${ODOO_CONF}"
    fi
elif [ -n "${USE_DB_STORAGE}" ] || [ -n "${DYNO}" ] || [ -n "${DIGITALOCEAN_APP_PLATFORM}" ]; then
    # Ephemeral filesystem detected — store attachments in database
    echo "" >> "${ODOO_CONF}"
    echo "ir_attachment.location = db" >> "${ODOO_CONF}"
fi

# -----------------------------------------------------------------------------
# Build database arguments
# -----------------------------------------------------------------------------
DB_ARGS=()
function check_config() {
    param="$1"
    value="$2"
    if grep -q -E "^\s*\b${param}\b\s*=" "$ODOO_RC" ; then
        value=$(grep -E "^\s*\b${param}\b\s*=" "$ODOO_RC" | cut -d " " -f3 | sed 's/["\n\r]//g')
    fi
    DB_ARGS+=("--${param}")
    DB_ARGS+=("${value}")
}
check_config "db_host" "$HOST"
check_config "db_port" "$DB_PORT"
check_config "db_user" "$USER"
check_config "db_password" "$PASSWORD"

case "$1" in
    -- | odoo)
        shift
        if [[ "$1" == "scaffold" ]] ; then
            exec odoo "$@"
        else
            wait-for-psql.py ${DB_ARGS[@]} --timeout=30
            exec odoo "$@" "${DB_ARGS[@]}"
        fi
        ;;
    -*)
        wait-for-psql.py ${DB_ARGS[@]} --timeout=30
        exec odoo "$@" "${DB_ARGS[@]}"
        ;;
    *)
        exec "$@"
esac

exit 1
