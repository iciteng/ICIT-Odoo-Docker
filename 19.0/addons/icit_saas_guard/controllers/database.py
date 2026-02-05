import logging
import re

from lxml import html as lxml_html

import odoo
import odoo.service.db
from odoo import http
from odoo.http import request, Response
from odoo.tools.misc import file_open
from odoo.addons.base.models.ir_qweb import render as qweb_render
from odoo.addons.web.controllers.database import Database, DBNAME_PATTERN

from ..utils import is_admin_subdomain

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Standalone branded 404 — works without DB context, no external deps
# ---------------------------------------------------------------------------
BRANDED_404_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>404 — Page Not Found</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{
  min-height:100vh;
  background:linear-gradient(135deg,#041c2c 0%,#0a2e4a 50%,#0d3b5e 100%);
  display:flex;align-items:center;justify-content:center;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  padding:1rem;
}
.card{
  width:100%;max-width:460px;
  background:rgba(255,255,255,.06);
  backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);
  border:1px solid rgba(47,167,226,.2);
  border-radius:1rem;
  box-shadow:0 8px 32px rgba(0,0,0,.4);
  text-align:center;
  padding:3rem 2rem;
  color:rgba(255,255,255,.85);
}
.logo{max-height:40px;margin-bottom:2rem;opacity:.7}
.code{font-size:5rem;font-weight:700;color:#2fa7e2;line-height:1}
h2{margin:.75rem 0;font-size:1.25rem;font-weight:500}
p{color:rgba(255,255,255,.45);margin-bottom:1.5rem;font-size:.9rem}
.btn{
  display:inline-block;padding:.6rem 2rem;
  background:#2fa7e2;color:#fff;text-decoration:none;
  border-radius:.5rem;font-weight:600;font-size:.9rem;
  transition:background .2s;
}
.btn:hover{background:#ff6d00}
.footer{
  margin-top:2rem;font-size:.7rem;color:rgba(255,255,255,.3);
  display:flex;align-items:center;justify-content:center;gap:.5rem;
}
.footer img{height:16px;opacity:.45}
.footer span{opacity:.3}
</style>
</head>
<body>
<div class="card">
  <img src="/icit_saas_guard/static/src/img/icit_logo.png" alt="ICIT" class="logo"/>
  <div class="code">404</div>
  <h2>Page Not Found</h2>
  <p>The page you're looking for doesn't exist or has been moved.</p>
  <a href="/web/login" class="btn">Back to Login</a>
  <div class="footer">
    <span>Powered by</span>
    <img src="/icit_saas_guard/static/src/img/odoo_logo_inverted.svg" alt="Odoo"/>
    <span>|</span>
    <img src="/icit_saas_guard/static/src/img/icit_logo.png" alt="ICIT"/>
  </div>
</div>
</body>
</html>"""


class DatabaseGuard(Database):
    """Guard all database routes to admin subdomain + branded dashboard."""

    def _is_admin_subdomain(self):
        return is_admin_subdomain()

    def _guard(self, route):
        """Return a branded 404 Response if not admin subdomain, else None."""
        if not self._is_admin_subdomain():
            host = request.httprequest.host
            _logger.warning("Blocked %s from non-admin host: %s", route, host)
            return Response(
                BRANDED_404_HTML,
                status=404,
                content_type='text/html; charset=utf-8',
            )
        return None

    # ------------------------------------------------------------------
    # Override _render_template to load ICIT branded dashboard templates
    # ------------------------------------------------------------------
    def _render_template(self, **d):
        d.setdefault('manage', True)
        d['insecure'] = odoo.tools.config.verify_admin_password('admin')
        d['list_db'] = odoo.tools.config['list_db']
        d['langs'] = odoo.service.db.exp_list_lang()
        d['countries'] = odoo.service.db.exp_list_countries()
        d['pattern'] = DBNAME_PATTERN

        try:
            d['databases'] = http.db_list()
            d['incompatible_databases'] = odoo.service.db.list_db_incompatible(
                d['databases']
            )
        except odoo.exceptions.AccessDenied:
            d['databases'] = [request.db] if request.db else []

        templates = {}
        with file_open(
            "icit_saas_guard/static/src/public/database_manager.qweb.html", "r"
        ) as fd:
            templates['database_manager'] = fd.read()
        with file_open(
            "icit_saas_guard/static/src/public/database_manager.master_input.qweb.html",
            "r",
        ) as fd:
            templates['master_input'] = fd.read()
        with file_open(
            "icit_saas_guard/static/src/public/database_manager.create_form.qweb.html",
            "r",
        ) as fd:
            templates['create_form'] = fd.read()
        with file_open(
            "icit_saas_guard/static/src/public/database_manager.apps_tab.qweb.html",
            "r",
        ) as fd:
            templates['apps_tab'] = fd.read()
        with file_open(
            "icit_saas_guard/static/src/public/database_manager.allowlist_modal.qweb.html",
            "r",
        ) as fd:
            templates['allowlist_modal'] = fd.read()

        def load(template_name):
            fromstring = (
                lxml_html.document_fromstring
                if template_name == 'database_manager'
                else lxml_html.fragment_fromstring
            )
            return (fromstring(templates[template_name]), template_name)

        return qweb_render('database_manager', d, load)

    # ------------------------------------------------------------------
    # Guarded routes — branded 404 for non-admin, branded dashboard for admin
    # ------------------------------------------------------------------
    @http.route('/web/database/selector', type='http', auth="none")
    def selector(self, **kw):
        blocked = self._guard('/web/database/selector')
        if blocked:
            return blocked
        return super().selector(**kw)

    @http.route('/web/database/manager', type='http', auth="none")
    def manager(self, **kw):
        blocked = self._guard('/web/database/manager')
        if blocked:
            return blocked
        if request.db:
            request.env.cr.close()
        return self._render_template()

    @http.route(
        '/web/database/create', type='http', auth="none",
        methods=['POST'], csrf=False,
    )
    def create(self, master_pwd, name, lang, password, **post):
        blocked = self._guard('/web/database/create')
        if blocked:
            return blocked
        return super().create(master_pwd, name, lang, password, **post)

    @http.route(
        '/web/database/duplicate', type='http', auth="none",
        methods=['POST'], csrf=False,
    )
    def duplicate(self, master_pwd, name, new_name, neutralize_database=False):
        blocked = self._guard('/web/database/duplicate')
        if blocked:
            return blocked
        return super().duplicate(
            master_pwd, name, new_name,
            neutralize_database=neutralize_database,
        )

    @http.route(
        '/web/database/drop', type='http', auth="none",
        methods=['POST'], csrf=False,
    )
    def drop(self, master_pwd, name):
        blocked = self._guard('/web/database/drop')
        if blocked:
            return blocked
        return super().drop(master_pwd, name)

    @http.route(
        '/web/database/backup', type='http', auth="none",
        methods=['POST'], csrf=False,
    )
    def backup(self, master_pwd, name, backup_format='zip', filestore=True):
        blocked = self._guard('/web/database/backup')
        if blocked:
            return blocked
        return super().backup(
            master_pwd, name, backup_format=backup_format, filestore=filestore,
        )

    @http.route(
        '/web/database/restore', type='http', auth="none",
        methods=['POST'], csrf=False, max_content_length=None,
    )
    def restore(
        self, master_pwd, backup_file, name,
        copy=False, neutralize_database=False,
    ):
        blocked = self._guard('/web/database/restore')
        if blocked:
            return blocked
        return super().restore(
            master_pwd, backup_file, name,
            copy=copy, neutralize_database=neutralize_database,
        )

    @http.route(
        '/web/database/change_password', type='http', auth="none",
        methods=['POST'], csrf=False,
    )
    def change_password(self, master_pwd, master_pwd_new):
        blocked = self._guard('/web/database/change_password')
        if blocked:
            return blocked
        return super().change_password(master_pwd, master_pwd_new)

    @http.route('/web/database/list', type='jsonrpc', auth='none')
    def list(self):
        if not self._is_admin_subdomain():
            host = request.httprequest.host
            _logger.warning(
                "Blocked /web/database/list from non-admin host: %s", host,
            )
            raise odoo.exceptions.AccessDenied("Database listing not available")
        return super().list()
