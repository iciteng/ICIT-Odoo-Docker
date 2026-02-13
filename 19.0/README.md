# Odoo 19.0 Docker Image (Folder Guide)

This folder contains everything needed to build and run an Odoo 19 container image.
The image is based on Ubuntu and installs Odoo from the official nightly `.deb` package.

This README documents only the `19.0/` folder and its runtime behavior.

## Contents

- `Dockerfile`: Builds the Odoo 19 image.
- `entrypoint.sh`: Startup logic that resolves DB settings, waits for PostgreSQL, then launches Odoo.
- `odoo.conf`: Default Odoo configuration file.
- `wait-for-psql.py`: Small utility used by the entrypoint to check database readiness.

## What This Image Builds

`19.0/Dockerfile` does the following:

1. Uses `ubuntu:noble` as the base image.
2. Installs runtime/build dependencies (Python libs, Node tooling, fonts, etc.).
3. Downloads and installs `wkhtmltopdf` package `0.12.6.1-3` (architecture-aware).
4. Installs `postgresql-client` from PGDG (`noble-pgdg` repo).
5. Installs `rtlcss` globally via npm.
6. Downloads and installs Odoo nightly `.deb`:
   - `ODOO_VERSION=19.0`
   - `ODOO_RELEASE=20260118`
   - SHA1 check with `ODOO_SHA=9cb5691e31d2d8831887e85cc07268016f522f4d`
7. Copies startup/config files into the image:
   - `/entrypoint.sh`
   - `/etc/odoo/odoo.conf`
   - `/usr/local/bin/wait-for-psql.py`
8. Creates writable addon mount at `/mnt/extra-addons`.
9. Declares volumes:
   - `/var/lib/odoo`
   - `/mnt/extra-addons`
10. Exposes ports:
    - `8069` (HTTP/XML-RPC)
    - `8071` (XML-RPCS)
    - `8072` (longpolling/livechat bus)
11. Sets default runtime:
    - `USER odoo`
    - `ENTRYPOINT ["/entrypoint.sh"]`
    - `CMD ["odoo"]`

## Build

From repo root:

```bash
docker build -t odoo:19-local ./19.0
```

Optional explicit architecture (usually not required when BuildKit already sets it):

```bash
docker build --build-arg TARGETARCH=amd64 -t odoo:19-local ./19.0
```

## Quick Start (Docker Compose)

Create `docker-compose.yml` in the repo root:

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: postgres
      POSTGRES_USER: odoo
      POSTGRES_PASSWORD: odoo
    volumes:
      - db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U odoo -d postgres"]
      interval: 5s
      timeout: 5s
      retries: 10

  odoo:
    build:
      context: ./19.0
    image: odoo:19-local
    depends_on:
      db:
        condition: service_healthy
    ports:
      - "8069:8069"
      - "8071:8071"
      - "8072:8072"
    environment:
      HOST: db
      PORT: 5432
      USER: odoo
      PASSWORD: odoo
    volumes:
      - odoo-data:/var/lib/odoo
      - ./addons:/mnt/extra-addons
    restart: unless-stopped

volumes:
  db-data:
  odoo-data:
```

Run:

```bash
docker compose up -d --build
```

Open:

- `http://localhost:8069`

## Quick Start (docker run)

Create PostgreSQL:

```bash
docker network create odoo-net

docker run -d \
  --name odoo-db \
  --network odoo-net \
  -e POSTGRES_DB=postgres \
  -e POSTGRES_USER=odoo \
  -e POSTGRES_PASSWORD=odoo \
  -v odoo-db-data:/var/lib/postgresql/data \
  postgres:16
```

Build and run Odoo:

```bash
docker build -t odoo:19-local ./19.0

docker run -d \
  --name odoo-web \
  --network odoo-net \
  -p 8069:8069 \
  -p 8071:8071 \
  -p 8072:8072 \
  -e HOST=odoo-db \
  -e PORT=5432 \
  -e USER=odoo \
  -e PASSWORD=odoo \
  -v odoo-web-data:/var/lib/odoo \
  -v ${PWD}/addons:/mnt/extra-addons \
  odoo:19-local
```

## Entrypoint Behavior (Important)

`entrypoint.sh` does database argument resolution and command dispatch.

### Environment Variable Resolution

The script resolves DB connection values in this order:

- `PASSWORD_FILE`:
  - If set, file contents override `PASSWORD`.
- `HOST` defaults:
  - `HOST`
  - `DB_PORT_5432_TCP_ADDR`
  - fallback `db`
- `PORT` defaults:
  - `PORT`
  - `DB_PORT`
  - `DB_PORT_5432_TCP_PORT`
  - fallback `5432`
- `USER` defaults:
  - `USER`
  - `DB_ENV_POSTGRES_USER`
  - `POSTGRES_USER`
  - fallback `odoo`
- `PASSWORD` defaults:
  - `PASSWORD`
  - `DB_ENV_POSTGRES_PASSWORD`
  - `POSTGRES_PASSWORD`
  - fallback `odoo`

### Config File Overrides

For each DB setting (`db_host`, `db_port`, `db_user`, `db_password`):

- If key exists in `$ODOO_RC` (`/etc/odoo/odoo.conf` by default), value from config file is used.
- Otherwise, resolved environment value is used.

This means explicit config-file DB values win over environment defaults.

### Wait-For-DB Gate

Before starting Odoo (for normal startup), entrypoint runs:

```bash
wait-for-psql.py --db_host ... --db_port ... --db_user ... --db_password ... --timeout=30
```

`wait-for-psql.py` attempts connection once per second until timeout.
On failure, container exits with:

- `Database connection failure: ...`

### Command Dispatch Rules

- If first arg is `odoo` or `--`:
  - For `scaffold`, run directly (no DB wait).
  - Otherwise wait for DB, then append DB args to Odoo command.
- If first arg starts with `-`:
  - Treated as Odoo options; waits for DB and appends DB args.
- Any other command:
  - Executed directly (useful for debugging shells or custom commands).

## Default Odoo Configuration

`odoo.conf` includes:

- `addons_path = /mnt/extra-addons`
- `data_dir = /var/lib/odoo`

Most options are present as commented defaults for quick tuning.

To use your own config, mount it and optionally set `ODOO_RC`:

```yaml
services:
  odoo:
    environment:
      ODOO_RC: /etc/odoo/odoo.conf
    volumes:
      - ./config/odoo.conf:/etc/odoo/odoo.conf:ro
```

## Volumes and Persistence

Use persistent volumes for:

- `/var/lib/odoo`: Odoo filestore and runtime data.
- PostgreSQL data directory (on DB container): actual database data.
- `/mnt/extra-addons`: custom addons (optional bind mount).

Without volume persistence, restarting/recreating containers can lose state.

## Common Operational Commands

Show Odoo logs:

```bash
docker compose logs -f odoo
```

Open shell in Odoo container:

```bash
docker compose exec odoo bash
```

Run a module upgrade:

```bash
docker compose exec odoo odoo -d <database_name> -u <module_name> --stop-after-init
```

Install a module:

```bash
docker compose exec odoo odoo -d <database_name> -i <module_name> --stop-after-init
```

## Database Backup and Restore (Basic)

Backup:

```bash
docker compose exec -T db pg_dump -U odoo -d <database_name> -Fc > backup.dump
```

Restore:

```bash
cat backup.dump | docker compose exec -T db pg_restore -U odoo -d <database_name> --clean --if-exists
```

Also back up `/var/lib/odoo` (filestore) for full consistency with DB backups.

## Production Notes

Minimum production hardening checklist:

1. Change default DB credentials.
2. Avoid publishing DB port publicly.
3. Put Odoo behind reverse proxy with TLS termination.
4. Set regular backup schedules for DB and filestore.
5. Pin image tags and control rollout process.
6. Use resource limits/reservations in Compose or orchestration platform.
7. Restrict addons to trusted code only.

## Troubleshooting

### `Database connection failure`

- Verify DB container is running.
- Check `HOST`, `PORT`, `USER`, `PASSWORD`.
- Confirm network connectivity between containers.
- Confirm database user permissions.

### Odoo starts but custom modules not visible

- Confirm mount path is exactly `/mnt/extra-addons`.
- Confirm `addons_path` includes `/mnt/extra-addons`.
- Check file permissions readable by user `odoo`.
- Update app list in Odoo UI.

### PDF/report rendering issues

- `wkhtmltopdf` is preinstalled, but missing fonts/assets can still affect output.
- Ensure required fonts are available for your language set.

### Permission errors in data/addons paths

- Ensure mounted host directories are writable/readable by container user `odoo`.
- Pre-create host dirs and adjust ownership/permissions.

## Updating the Pinned Odoo Nightly Build

`19.0/Dockerfile` pins both release and SHA. To update:

1. Change `ODOO_RELEASE` to desired nightly build identifier.
2. Download the matching `.deb`.
3. Compute SHA1:
   ```bash
   sha1sum odoo_19.0.<release>_all.deb
   ```
4. Update `ODOO_SHA` accordingly.
5. Rebuild and run a smoke test (`/web`, module install, PDF generation).

This keeps builds deterministic and tamper-checked.

## File References

- `19.0/Dockerfile`
- `19.0/entrypoint.sh`
- `19.0/odoo.conf`
- `19.0/wait-for-psql.py`
