#!/bin/bash

set -e

if [ -v PASSWORD_FILE ]; then
    PASSWORD="$(< $PASSWORD_FILE)"
fi

# set the postgres database host, port, user and password according to the environment
# and pass them as arguments to the odoo process if not present in the config file
: ${HOST:=${DB_PORT_5432_TCP_ADDR:='db'}}
: ${DB_PORT:=${DB_PORT_5432_TCP_PORT:=5432}}
: ${USER:=${DB_ENV_POSTGRES_USER:=${POSTGRES_USER:='odoo'}}}
: ${PASSWORD:=${DB_ENV_POSTGRES_PASSWORD:=${POSTGRES_PASSWORD:='odoo'}}}
: ${DB_NAME:='postgres'}
: ${DB_SSLMODE:=''}

DB_ARGS=()
function check_config() {
    param="$1"
    value="$2"
    if grep -q -E "^\s*\b${param}\b\s*=" "$ODOO_RC" ; then
        value=$(grep -E "^\s*\b${param}\b\s*=" "$ODOO_RC" |cut -d " " -f3|sed 's/["\n\r]//g')
    fi;
    DB_ARGS+=("--${param}")
    DB_ARGS+=("${value}")
}
check_config "db_host" "$HOST"
check_config "db_port" "$DB_PORT"
check_config "db_user" "$USER"
check_config "db_password" "$PASSWORD"

# Build wait-for-psql args (subset that the script supports)
WAIT_ARGS=("--db_host" "$HOST" "--db_port" "$DB_PORT" "--db_user" "$USER" "--db_password" "$PASSWORD" "--db_name" "$DB_NAME")
if [ -n "$DB_SSLMODE" ]; then
    check_config "db_sslmode" "$DB_SSLMODE"
    WAIT_ARGS+=("--db_sslmode" "$DB_SSLMODE")
fi

# -----------------------------------------------------------------------------
# Pre-install modules on first boot (idempotent via sentinel file)
# -----------------------------------------------------------------------------
function maybe_init_modules() {
    if [ -z "${ODOO_INIT_MODULES:-}" ]; then
        return 0
    fi

    MODULES_HASH=$(echo -n "$ODOO_INIT_MODULES" | md5sum | cut -d' ' -f1)
    MODULES_SENTINEL="/var/lib/odoo/.modules_init_${MODULES_HASH}"

    if [ -f "${MODULES_SENTINEL}" ]; then
        echo "Modules already initialized (hash: ${MODULES_HASH}), skipping"
        return 0
    fi

    if [ -z "${DB_NAME:-}" ] || [ "$DB_NAME" = "postgres" ]; then
        echo "WARNING: ODOO_INIT_MODULES set but DB_NAME not specified, skipping pre-install" >&2
        return 0
    fi

    echo "Pre-installing modules: ${ODOO_INIT_MODULES} into database ${DB_NAME}..."
    set +e
    odoo -d "$DB_NAME" -i "$ODOO_INIT_MODULES" --without-demo=all --stop-after-init "${DB_ARGS[@]}"
    MODULES_INIT_EXIT_CODE=$?
    set -e

    if [ "${MODULES_INIT_EXIT_CODE}" -eq 0 ]; then
        touch "${MODULES_SENTINEL}"
        echo "Module pre-install completed successfully"
    else
        echo "WARNING: Module pre-install failed (exit code: ${MODULES_INIT_EXIT_CODE}), continuing startup..." >&2
    fi
}

case "$1" in
    -- | odoo)
        shift
        if [[ "$1" == "scaffold" ]] ; then
            exec odoo "$@"
        else
            wait-for-psql.py "${WAIT_ARGS[@]}" --timeout=30
            maybe_init_modules
            exec odoo "$@" "${DB_ARGS[@]}"
        fi
        ;;
    -*)
        wait-for-psql.py "${WAIT_ARGS[@]}" --timeout=30
        maybe_init_modules
        exec odoo "$@" "${DB_ARGS[@]}"
        ;;
    *)
        exec "$@"
esac

exit 1
