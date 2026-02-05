from odoo.addons.web.controllers.home import Home
from odoo.http import request, route

from ..utils import is_admin_subdomain


class HomeGuard(Home):

    @route('/web/login', type='http', auth='none')
    def web_login(self, redirect=None, **kw):
        response = super().web_login(redirect=redirect, **kw)
        if hasattr(response, 'qcontext'):
            response.qcontext['is_admin'] = is_admin_subdomain()
        return response

    @route('/', type='http', auth='none')
    def admin_root_redirect(self, **kw):
        """Redirect admin subdomain root to the ops dashboard."""
        if is_admin_subdomain():
            return request.redirect('/web/database/manager')
        return request.redirect('/odoo')
