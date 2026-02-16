from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.home import Home


class CustomHome(Home):
    def _is_icit_admin(self, user):
        login = (user.login or '').strip().lower()
        return user.has_group('saas_manager.group_icit_admin') and login.endswith('@icitsolutions.com')

    @http.route('/', type='http', auth='public')
    def index(self, **kwargs):
        if request.session.uid:
            return request.redirect('/odoo')
        values = {
            'error': kwargs.get('error'),
        }
        return request.render('custom_auth.login_page', values)

    @http.route('/web/database/selector', type='http', auth='none')
    def database_selector(self, **kwargs):
        return request.render('custom_auth.error_404', {}, status=404)

    @http.route('/web/database/manager', type='http', auth='none')
    def database_manager(self, **kwargs):
        return request.render('custom_auth.error_404', {}, status=404)

    @http.route('/web/login', type='http', auth='none')
    def web_login(self, redirect=None, **kwargs):
        if request.session.uid:
            user = request.env['res.users'].browse(request.session.uid)
            if user.exists() and self._is_icit_admin(user):
                return request.redirect('/admin')
            return request.redirect('/odoo')

        target = (redirect or kwargs.get('redirect') or '').strip()
        if target.startswith('/admin'):
            return request.redirect('/admin')
        return request.redirect('/')


class CustomAuthController(http.Controller):

    def _is_icit_admin(self, user):
        login = (user.login or '').strip().lower()
        return user.has_group('saas_manager.group_icit_admin') and login.endswith('@icitsolutions.com')

    def _authenticate(self, login, password):
        credential = {'login': login, 'password': password, 'type': 'password'}
        request.session.authenticate(request.env, credential)
        return request.session.uid

    @http.route('/auth/login', type='http', auth='public', methods=['POST'], csrf=True)
    def auth_login(self, login=None, password=None, **kwargs):
        try:
            uid = self._authenticate(login, password)
            if uid:
                return request.redirect('/odoo')
        except Exception:
            pass
        return request.redirect('/?error=1')

    @http.route('/admin', type='http', auth='public')
    def admin_panel(self, **kwargs):
        if request.session.uid:
            user = request.env['res.users'].browse(request.session.uid)
            login = (user.login or '').strip().lower()
            is_icit_admin = user.has_group('saas_manager.group_icit_admin') and login.endswith('@icitsolutions.com')
            if is_icit_admin:
                return request.render('saas_manager.admin_dashboard', {'user_name': user.name})
            return request.render('saas_manager.admin_access_denied')
        values = {
            'error': kwargs.get('error'),
        }
        return request.render('custom_auth.admin_login_page', values)

    @http.route('/admin/login', type='http', auth='public', methods=['POST'], csrf=True)
    def admin_login(self, login=None, password=None, **kwargs):
        try:
            uid = self._authenticate(login, password)
            if uid:
                user = request.env['res.users'].sudo().browse(uid)
                email_ok = (user.login or '').strip().lower().endswith('@icitsolutions.com')
                group_ok = request.env['res.users'].browse(uid).has_group('saas_manager.group_icit_admin')
                if email_ok and group_ok:
                    return request.redirect('/admin')
                request.session.logout()
                return request.redirect('/admin?error=access_denied')
        except Exception:
            pass
        return request.redirect('/admin?error=1')

    @http.route('/auth/logout', type='http', auth='public', methods=['GET'], csrf=False)
    def auth_logout(self, next=None, **kwargs):
        redirect_target = '/'

        uid = request.session.uid
        if uid:
            user = request.env['res.users'].sudo().browse(uid)
            if user.exists() and self._is_icit_admin(user):
                redirect_target = '/admin'

        if (next or '').strip().lower() == 'admin':
            redirect_target = '/admin'

        request.session.logout()
        return request.redirect(redirect_target)
