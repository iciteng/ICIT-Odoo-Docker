import os

import odoo.http

ADMIN_SUBDOMAIN = os.environ.get('ADMIN_SUBDOMAIN', 'admin')


def is_admin_subdomain(host=None):
    """Check if the current request is from the admin subdomain."""
    if host is None:
        try:
            host = odoo.http.request.httprequest.host
        except Exception:
            return False
    hostname = host.split(':')[0]
    return hostname.split('.')[0] == ADMIN_SUBDOMAIN


_original_db_filter = odoo.http.db_filter


def _patched_db_filter(dbs, host=None):
    """Admin subdomain sees ALL databases, others get normal dbfilter."""
    if is_admin_subdomain(host):
        return list(dbs)
    return _original_db_filter(dbs, host)


def patch_db_filter():
    odoo.http.db_filter = _patched_db_filter
