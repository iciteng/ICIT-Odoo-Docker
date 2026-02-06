# ICIT SaaS Guard -- Odoo 19 Multi-Tenant Docker

Production-ready Odoo 19 Docker image with **ICIT SaaS Guard v4** for multi-tenant SaaS deployments on DigitalOcean App Platform.

## What is ICIT SaaS Guard?

A server-wide Odoo module (`icit_saas_guard`) that adds:

- **Admin subdomain guard** -- All `/web/database/*` routes are restricted to the `admin` subdomain. Non-admin subdomains get a branded 404.
- **Subdomain-based tenant routing** -- `tenant.yourdomain.com` routes to database `tenant` via Odoo's `dbfilter = ^%d$`.
- **Branded ops dashboard** -- Replaces the default database manager with a tabbed UI (Databases + App Manager).
- **Per-tenant app management** -- Install, uninstall, and upgrade modules across tenant databases with HMAC-signed auth tokens.
- **App allowlisting** -- Control which modules tenants can access (allowlist/denylist/disabled modes).
- **Branded login page** -- Dark glassmorphism theme at priority 99, immune to tenant module overrides.
- **Branded 404 pages** -- Standalone HTML (no DB context needed) for guard responses.

## Architecture

```
                    *.yourdomain.com
                          |
                    DO App Platform
                          |
                    +-----+-----+
                    |   Odoo    |
                    | (Port 8069)|
                    +-----+-----+
                          |
              +-----------+-----------+
              |                       |
     admin.yourdomain.com    tenant.yourdomain.com
              |                       |
     Ops Dashboard            Tenant DB (dbfilter)
     DB Manager               Login / App
     App Manager
```

- **Python code** (controllers, monkey-patches) loads for ALL requests via `server_wide_modules`.
- **Template XML + SCSS** are per-database (ir.ui.view + asset bundles).
- The database manager uses standalone QWeb (`qweb_render()` + `file_open()`), NOT ir.ui.view -- template inheritance doesn't work there. The controller overrides `_render_template()` directly.

## Project Structure

```
19.0/
  Dockerfile              # Ubuntu Noble + Odoo 19 + boto3/s3fs
  entrypoint.sh           # DB connection, admin password, S3/Spaces config
  odoo.prod.conf          # Production config (workers, limits, proxy_mode)
  odoo.dev.conf           # Development config (workers=0, no SSL)
  docker-compose.yml      # Local development
  docker-compose.prod.yml # Local production testing
  app.yaml                # DO App Platform spec
  .env.prod.example       # Environment variable reference
  .dockerignore           # Excludes dev artifacts from Docker build
  wait-for-psql.py        # Waits for PostgreSQL before starting Odoo
  addons/
    icit_saas_guard/       # The SaaS Guard module (v19.0.4.0.0)
      controllers/
        database.py        # Guard + branded dashboard + app manager API
        apps.py            # Module management (install/uninstall/upgrade)
        home.py            # Admin homepage redirect
        website_guard.py   # Frontend 404 for non-tenant subdomains
      allowlist.py         # Per-tenant module allowlisting
      utils.py             # Subdomain detection + db_filter patch
      static/src/
        public/            # QWeb templates for dashboard UI
        scss/              # Branded login styles
        img/               # ICIT logo assets
      views/
        login_templates.xml # Login page template overrides
```

## Quick Start (Local Development)

```bash
cd 19.0
docker compose up -d
```

Odoo is at `http://localhost:8069`. The SaaS Guard loads automatically via `server_wide_modules = base,web,icit_saas_guard`.

### Accessing from another machine on LAN

Docker Desktop with WSL2 requires a port proxy for LAN access:

```powershell
# Run in Admin PowerShell on the host machine
netsh interface portproxy add v4tov4 listenport=8069 listenaddress=0.0.0.0 connectport=8069 connectaddress=127.0.0.1

# Also allow through Windows Firewall
New-NetFirewallRule -DisplayName 'Odoo Dev (8069)' -Direction Inbound -Protocol TCP -LocalPort 8069 -Action Allow
```

On the client machine, add to `/etc/hosts` (or `C:\Windows\System32\drivers\etc\hosts`):

```
192.168.1.x admin.odoo.local odoo.local
```

Then visit `http://admin.odoo.local:8069/web/database/manager`.

## Production Deployment (DO App Platform)

### Prerequisites

- DigitalOcean account with App Platform access
- GitHub repo connected to DO (`iciteng/ICIT-Odoo-Docker`)
- A domain with wildcard DNS support

### Deploy

```bash
doctl apps create --spec 19.0/app.yaml
```

Or create via the DO console: **App Platform > Create App > GitHub > `iciteng/ICIT-Odoo-Docker` > branch `silly-sanderson` > source dir `19.0`**.

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `HOST` | Yes | PostgreSQL hostname (use `${db.HOSTNAME}` for managed DB) |
| `DB_PORT` | Yes | PostgreSQL port (use `${db.PORT}` -- **not** `PORT`, which DO reserves for HTTP) |
| `USER` | Yes | PostgreSQL username |
| `PASSWORD` | Yes | PostgreSQL password (SECRET) |
| `DB_SSLMODE` | Yes | `require` for managed DB, `disable` for local |
| `ODOO_ADMIN_PASSWD` | Yes | Master password for DB management (SECRET) |
| `ADMIN_SUBDOMAIN` | No | Subdomain for admin access (default: `admin`) |
| `SPACES_BUCKET` | No | DO Spaces bucket name for attachment storage |
| `SPACES_ENDPOINT` | No | Spaces endpoint (e.g., `https://nyc3.digitaloceanspaces.com`) |
| `SPACES_ACCESS_KEY` | No | Spaces access key (SECRET) |
| `SPACES_SECRET_KEY` | No | Spaces secret key (SECRET) |

**Important:** DO App Platform injects `PORT` as the HTTP listener port (8069). The entrypoint uses `DB_PORT` for the database connection to avoid this collision.

### DNS Configuration

For multi-tenant subdomain routing:

1. Add a wildcard CNAME: `*.yourdomain.com` -> `your-app.ondigitalocean.app`
2. Add root CNAME: `yourdomain.com` -> `your-app.ondigitalocean.app`
3. In DO console, add both domains to the app
4. DO auto-provisions Let's Encrypt SSL (including wildcard)

### Post-Deploy Verification

1. `https://yourdomain.com/web/health` -- should return OK
2. `https://admin.yourdomain.com/web/database/manager` -- ICIT branded dashboard
3. Create a tenant database named `demo`
4. `https://demo.yourdomain.com/web/login` -- routes to `demo` database
5. `https://random.yourdomain.com/` -- branded 404 (guard blocks)

## Key Design Decisions

### Why `DB_PORT` instead of `PORT`?

DO App Platform injects `PORT=8069` (the HTTP port) into the container environment. The entrypoint originally used `PORT` for both HTTP and DB connections, causing Odoo to try connecting to PostgreSQL on port 8069. The fix uses `DB_PORT` exclusively for database connections.

### Why `chmod +x` in Dockerfile?

Windows git checkouts strip execute permissions from shell scripts. The Dockerfile explicitly runs `chmod +x /entrypoint.sh` after `COPY` to ensure it's executable in the container.

### Why `COPY ./addons` before `VOLUME`?

App Platform builds Docker images from the git repo -- there's no volume mount for addons. The `COPY --chown=odoo:odoo ./addons /mnt/extra-addons` line bakes the addon into the image. The `VOLUME` declaration after it still allows bind-mount override in local development.

### Attachment Storage

- **With S3/Spaces addon:** Entrypoint detects `SPACES_*` env vars + OCA addon and configures `ir_attachment.location = s3`
- **Without S3 addon:** Falls back to `ir_attachment.location = db` (attachments stored in PostgreSQL)
- **Local dev:** Uses filesystem (default Odoo behavior)

### Allowlist Persistence

The allowlist JSON is stored at `{data_dir}/saas_guard/allowlists.json`. On App Platform (ephemeral filesystem), this file is lost on every deploy/restart. For MVP this is acceptable -- allowlists can be reconfigured post-deploy. Future fix: store in DO Spaces or a dedicated DB table.

## Configuration Files

| File | Purpose |
|------|---------|
| `odoo.prod.conf` | Production: `proxy_mode=True`, `workers=2`, `db_maxconn=5`, tuned for 1GB managed PG |
| `odoo.dev.conf` | Development: `workers=0`, no SSL, `admin_passwd=odoo` |
| `docker-compose.yml` | Local dev with bind-mounted addons |
| `docker-compose.prod.yml` | Local production testing (baked addons, health checks) |
| `app.yaml` | DO App Platform deployment spec |
| `.env.prod.example` | Reference for all production environment variables |

## License

ICIT SaaS Guard: LGPL-3 | Odoo Docker image: MIT
