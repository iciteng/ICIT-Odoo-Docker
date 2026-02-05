{
    'name': 'ICIT SaaS Guard',
    'version': '19.0.4.0.0',
    'category': 'Tools',
    'summary': 'Admin subdomain guard, branded login, ops dashboard with app management for multi-tenant SaaS',
    'description': """
Restricts all /web/database/* routes to the admin subdomain.
Patches db_filter so admin subdomain sees all databases.
Dark glassmorphism branded login page (priority 99 — immune to tenant modules).
Custom ops dashboard replacing /web/database/manager with tabbed UI.
Per-tenant app management: install, uninstall, upgrade modules across databases.
App allowlisting: allowlist/denylist/disabled modes per tenant.
HMAC-signed auth tokens (30-min TTL) for secure module operations.
Branded 404 pages (standalone + frontend).
Admin subdomain homepage redirect to ops dashboard.
Loaded as a server-wide module so it works without database context.
Configure ADMIN_SUBDOMAIN env var (default: "admin").
    """,
    'author': 'ICIT Solutions',
    'depends': ['web', 'http_routing'],
    'data': [
        'views/login_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'icit_saas_guard/static/src/scss/login.scss',
        ],
    },
    'auto_install': True,
    'license': 'LGPL-3',
}
