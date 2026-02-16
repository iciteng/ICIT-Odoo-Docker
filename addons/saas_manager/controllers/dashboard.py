import logging
from datetime import timedelta

from odoo import fields, http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

from ..models.app_group_mapping import get_app_groups

_logger = logging.getLogger(__name__)


class SaasDashboardController(http.Controller):

    def _json_error(self, message, status=400):
        return {'error': message, 'status': status}

    def _check_icit_admin(self):
        uid = request.session.uid
        if not uid:
            raise AccessError('Authentication required.')

        user = request.env['res.users'].browse(uid)
        if not user.exists():
            raise AccessError('User not found.')

        login = (user.login or '').strip().lower()
        is_icit_admin = user.has_group('saas_manager.group_icit_admin') and login.endswith('@icitsolutions.com')
        if not is_icit_admin:
            raise AccessError('Access denied.')
        return user

    @http.route('/admin/api/stats', type='jsonrpc', auth='user', methods=['POST'], csrf=False)
    def get_stats(self, **kwargs):
        try:
            self._check_icit_admin()
            tenant_model = request.env['saas.tenant'].sudo()
            usage_model = request.env['saas.usage.log'].sudo()
            users_model = request.env['res.users'].sudo()

            tenants = tenant_model.search([])
            total_tenants = len(tenants)
            active_today = tenant_model.search_count([('status', '=', 'active')])

            company_ids = tenants.mapped('company_id').ids
            total_users = users_model.search_count([('company_id', 'in', company_ids)]) if company_ids else 0

            storage_mb = 0.0
            for tenant in tenants:
                latest_log = usage_model.search([('tenant_id', '=', tenant.id)], order='date desc, id desc', limit=1)
                storage_mb += latest_log.storage_mb if latest_log else 0.0

            return {
                'total_tenants': total_tenants,
                'active_today': active_today,
                'total_users': total_users,
                'storage_mb': storage_mb,
            }
        except AccessError as exc:
            return self._json_error(str(exc), status=403)
        except Exception:
            _logger.exception('Failed to fetch SaaS dashboard stats.')
            return self._json_error('Failed to fetch dashboard stats.', status=500)

    @http.route('/admin/api/tenants/list', type='jsonrpc', auth='user', methods=['POST'], csrf=False)
    def get_tenants(self, **kwargs):
        try:
            self._check_icit_admin()
            tenant_model = request.env['saas.tenant'].sudo()
            users_model = request.env['res.users'].sudo()
            tenants = tenant_model.search([], order='id desc')

            items = []
            for tenant in tenants:
                user_count = users_model.search_count([('company_id', '=', tenant.company_id.id)])
                items.append({
                    'id': tenant.id,
                    'company_name': tenant.company_id.name,
                    'status': tenant.status,
                    'plan': tenant.plan,
                    'max_users': tenant.max_users,
                    'user_count': user_count,
                    'admin_email': tenant.admin_user_id.login or '',
                    'admin_name': tenant.admin_user_id.name or '',
                    'created_date': str(tenant.created_date) if tenant.created_date else '',
                })

            return {'tenants': items}
        except AccessError as exc:
            return self._json_error(str(exc), status=403)
        except Exception:
            _logger.exception('Failed to fetch SaaS tenants.')
            return self._json_error('Failed to fetch tenants.', status=500)

    @http.route('/admin/api/tenants', type='jsonrpc', auth='user', methods=['POST'], csrf=False)
    def create_tenant(self, **kwargs):
        try:
            self._check_icit_admin()
            company_name = (kwargs.get('company_name') or '').strip()
            admin_email = (kwargs.get('admin_email') or '').strip()
            admin_name = (kwargs.get('admin_name') or '').strip()
            admin_password = (kwargs.get('admin_password') or '').strip()
            plan = (kwargs.get('plan') or 'free').strip().lower()
            max_users = int(kwargs.get('max_users') or 5)
            allowed_plans = {'free', 'basic', 'pro', 'enterprise'}

            if not company_name or not admin_email or not admin_name:
                raise ValidationError('Company name, admin email, and admin name are required.')
            if not admin_password:
                raise ValidationError('Admin password is required.')
            if plan == 'trial':
                plan = 'free'
            if plan not in allowed_plans:
                raise ValidationError('Invalid plan value.')
            if max_users < 1:
                raise ValidationError('Max users must be at least 1.')

            cr = request.env.cr
            cr.execute('SAVEPOINT create_tenant_sp')
            try:
                company = request.env['res.company'].sudo().create({
                    'name': company_name,
                })

                admin_user = request.env['res.users'].sudo().create({
                    'name': admin_name,
                    'login': admin_email,
                    'email': admin_email,
                    'password': admin_password,
                    'company_id': company.id,
                    'company_ids': [(6, 0, [company.id])],
                    'group_ids': [(4, request.env.ref('base.group_user').id)],
                })

                tenant = request.env['saas.tenant'].sudo().create({
                    'name': company_name,
                    'company_id': company.id,
                    'plan': plan,
                    'max_users': max_users,
                    'admin_user_id': admin_user.id,
                })

                cr.execute('RELEASE SAVEPOINT create_tenant_sp')
                return {'success': True, 'id': tenant.id}
            except Exception:
                cr.execute('ROLLBACK TO SAVEPOINT create_tenant_sp')
                raise
        except AccessError as exc:
            return self._json_error(str(exc), status=403)
        except (ValidationError, ValueError) as exc:
            return self._json_error(str(exc), status=400)
        except Exception:
            _logger.exception('Failed to create SaaS tenant.')
            return self._json_error('Failed to create tenant.', status=500)

    @http.route('/admin/api/tenants/<int:tenant_id>/update', type='jsonrpc', auth='user', methods=['POST'], csrf=False)
    def update_tenant(self, tenant_id, **kwargs):
        try:
            self._check_icit_admin()
            tenant = request.env['saas.tenant'].sudo().browse(tenant_id)
            if not tenant.exists():
                return self._json_error('Tenant not found.', status=404)

            tenant_vals = {}
            if 'status' in kwargs:
                status = (kwargs.get('status') or '').strip().lower()
                if status not in {'active', 'suspended', 'trial'}:
                    raise ValidationError('Invalid status value.')
                tenant_vals['status'] = status
            if 'plan' in kwargs:
                plan = (kwargs.get('plan') or '').strip().lower()
                if plan == 'trial':
                    tenant_vals['status'] = 'trial'
                    tenant_vals['plan'] = 'free'
                elif plan in {'free', 'basic', 'pro', 'enterprise'}:
                    tenant_vals['plan'] = plan
                elif plan:
                    raise ValidationError('Invalid plan value.')
            if 'max_users' in kwargs and kwargs.get('max_users') is not None:
                max_users = int(kwargs.get('max_users'))
                if max_users < 1:
                    raise ValidationError('Max users must be at least 1.')
                tenant_vals['max_users'] = max_users

            if tenant_vals:
                tenant.write(tenant_vals)

            if 'company_name' in kwargs and tenant.company_id:
                company_name = (kwargs.get('company_name') or '').strip()
                if company_name:
                    tenant.company_id.sudo().write({'name': company_name})
                    tenant.write({'name': company_name})

            if tenant.admin_user_id:
                admin_user_vals = {}
                if 'admin_email' in kwargs:
                    admin_email = (kwargs.get('admin_email') or '').strip()
                    if admin_email:
                        admin_user_vals.update({'login': admin_email, 'email': admin_email})
                if 'admin_name' in kwargs:
                    admin_name = (kwargs.get('admin_name') or '').strip()
                    if admin_name:
                        admin_user_vals['name'] = admin_name
                if admin_user_vals:
                    tenant.admin_user_id.sudo().write(admin_user_vals)

            return {'success': True}
        except AccessError as exc:
            return self._json_error(str(exc), status=403)
        except (ValidationError, ValueError) as exc:
            return self._json_error(str(exc), status=400)
        except Exception:
            _logger.exception('Failed to update SaaS tenant %s.', tenant_id)
            return self._json_error('Failed to update tenant.', status=500)

    @http.route('/admin/api/tenants/<int:tenant_id>/delete', type='jsonrpc', auth='user', methods=['POST'], csrf=False)
    def delete_tenant(self, tenant_id, **kwargs):
        try:
            self._check_icit_admin()
            tenant = request.env['saas.tenant'].sudo().browse(tenant_id)
            if not tenant.exists():
                return self._json_error('Tenant not found.', status=404)
            tenant.action_suspend()
            return {'success': True}
        except AccessError as exc:
            return self._json_error(str(exc), status=403)
        except Exception:
            _logger.exception('Failed to suspend SaaS tenant %s.', tenant_id)
            return self._json_error('Failed to delete tenant.', status=500)

    @http.route('/admin/api/tenants/<int:tenant_id>/users', type='jsonrpc', auth='user', methods=['POST'], csrf=False)
    def get_tenant_users(self, tenant_id, **kwargs):
        try:
            self._check_icit_admin()
            tenant = request.env['saas.tenant'].sudo().browse(tenant_id)
            if not tenant.exists():
                return self._json_error('Tenant not found.', status=404)

            users = request.env['res.users'].sudo().search([('company_id', '=', tenant.company_id.id)], order='name asc')
            items = [{'name': user.name or '', 'login': user.login or ''} for user in users]
            return {'users': items}
        except AccessError as exc:
            return self._json_error(str(exc), status=403)
        except Exception:
            _logger.exception('Failed to fetch users for SaaS tenant %s.', tenant_id)
            return self._json_error('Failed to fetch tenant users.', status=500)

    @http.route('/admin/api/tenants/<int:tenant_id>/apps', type='jsonrpc', auth='user', methods=['POST'], csrf=False)
    def get_tenant_apps(self, tenant_id, **kwargs):
        try:
            self._check_icit_admin()
            tenant = request.env['saas.tenant'].sudo().browse(tenant_id)
            if not tenant.exists():
                return self._json_error('Tenant not found.', status=404)

            all_apps = request.env['ir.module.module'].sudo().search([
                ('application', '=', True),
                ('state', '!=', 'uninstallable'),
            ], order='shortdesc asc, name asc')

            enabled_ids = set(tenant.allowed_app_ids.ids)

            apps = []
            for mod in all_apps:
                apps.append({
                    'id': mod.id,
                    'name': mod.shortdesc or mod.name,
                    'technical_name': mod.name,
                    'enabled': mod.id in enabled_ids,
                    'installed': mod.state in ('installed', 'to upgrade'),
                })
            return {'apps': apps}
        except AccessError as exc:
            return self._json_error(str(exc), status=403)
        except Exception:
            _logger.exception('Failed to fetch apps for SaaS tenant %s.', tenant_id)
            return self._json_error('Failed to fetch tenant apps.', status=500)

    @http.route('/admin/api/tenants/<int:tenant_id>/apps/<int:app_id>', type='jsonrpc', auth='user', methods=['POST'], csrf=False)
    def set_tenant_app_access(self, tenant_id, app_id, **kwargs):
        try:
            self._check_icit_admin()
            tenant = request.env['saas.tenant'].sudo().browse(tenant_id)
            if not tenant.exists():
                return self._json_error('Tenant not found.', status=404)

            module = request.env['ir.module.module'].sudo().browse(app_id)
            if not module.exists():
                return self._json_error('App not found.', status=404)

            enabled_param = kwargs.get('enabled')
            if isinstance(enabled_param, str):
                enabled = enabled_param.strip().lower() in {'1', 'true', 'yes', 'on'}
            else:
                enabled = bool(enabled_param)

            if enabled:
                if module.state not in ('installed', 'to upgrade'):
                    return self._json_error(
                        'Module is not pre-installed. Contact support.',
                        status=409,
                    )

                app_groups = get_app_groups(request.env, module.name)

                company_users = request.env['res.users'].sudo().search([
                    ('company_id', '=', tenant.company_id.id),
                ])
                if app_groups and company_users:
                    group_cmds = [(4, g.id) for g in app_groups]
                    for user in company_users:
                        user.write({'groups_id': group_cmds})

                tenant.write({'allowed_app_ids': [(4, module.id)]})
            else:
                app_groups = get_app_groups(request.env, module.name)

                other_enabled = tenant.allowed_app_ids - module
                shared_groups = request.env['res.groups']
                for other_mod in other_enabled:
                    shared_groups |= get_app_groups(request.env, other_mod.name)

                groups_to_remove = app_groups - shared_groups

                company_users = request.env['res.users'].sudo().search([
                    ('company_id', '=', tenant.company_id.id),
                ])
                if groups_to_remove and company_users:
                    group_cmds = [(3, g.id) for g in groups_to_remove]
                    for user in company_users:
                        user.write({'groups_id': group_cmds})

                tenant.write({'allowed_app_ids': [(3, module.id)]})

            access_model = request.env['saas.app.access'].sudo()
            access = access_model.search([
                ('tenant_id', '=', tenant.id),
                ('module_id', '=', module.id),
            ], limit=1)
            if access:
                access.write({'enabled': enabled})
            else:
                access_model.create({
                    'tenant_id': tenant.id,
                    'module_id': module.id,
                    'enabled': enabled,
                })

            return {'success': True}
        except AccessError as exc:
            return self._json_error(str(exc), status=403)
        except Exception:
            _logger.exception(
                'Failed to update app access for tenant %s and app %s.',
                tenant_id, app_id,
            )
            return self._json_error('Failed to update app access.', status=500)

    @http.route('/admin/api/tenants/<int:tenant_id>/usage', type='jsonrpc', auth='user', methods=['POST'], csrf=False)
    def get_tenant_usage(self, tenant_id, **kwargs):
        try:
            self._check_icit_admin()
            tenant = request.env['saas.tenant'].sudo().browse(tenant_id)
            if not tenant.exists():
                return self._json_error('Tenant not found.', status=404)

            start_date = fields.Date.today() - timedelta(days=29)
            logs = request.env['saas.usage.log'].sudo().search(
                [('tenant_id', '=', tenant.id), ('date', '>=', start_date)],
                order='date asc',
            )

            usage = [{
                'date': str(log.date) if log.date else '',
                'login_count': log.login_count,
            } for log in logs]
            return {'usage': usage}
        except AccessError as exc:
            return self._json_error(str(exc), status=403)
        except Exception:
            _logger.exception('Failed to fetch usage for SaaS tenant %s.', tenant_id)
            return self._json_error('Failed to fetch usage data.', status=500)

    @http.route('/admin/api/admins', type='jsonrpc', auth='user', methods=['POST'], csrf=False)
    def get_admins(self, **kwargs):
        try:
            self._check_icit_admin()
            group = request.env.ref('saas_manager.group_icit_admin')
            admin_users = request.env['res.users'].sudo().search([
                ('group_ids', 'in', [group.id]),
            ], order='name asc')

            items = [{
                'id': u.id,
                'name': u.name or '',
                'login': u.login or '',
            } for u in admin_users]
            return {'admins': items}
        except AccessError as exc:
            return self._json_error(str(exc), status=403)
        except Exception:
            _logger.exception('Failed to fetch admin users.')
            return self._json_error('Failed to fetch admin users.', status=500)

    @http.route('/admin/api/admins/add', type='jsonrpc', auth='user', methods=['POST'], csrf=False)
    def add_admin(self, **kwargs):
        try:
            self._check_icit_admin()
            email = (kwargs.get('email') or '').strip().lower()
            name = (kwargs.get('name') or '').strip()
            password = (kwargs.get('password') or '').strip()

            if not email or not name or not password:
                raise ValidationError('Email, name, and password are required.')
            if not email.endswith('@icitsolutions.com'):
                raise ValidationError('Only @icitsolutions.com emails can be ICIT admins.')

            users_model = request.env['res.users'].sudo()
            existing = users_model.search([('login', '=', email)], limit=1)

            icit_group = request.env.ref('saas_manager.group_icit_admin')

            if existing:
                if icit_group.id in existing.group_ids.ids:
                    raise ValidationError('User already has admin access.')
                existing.write({'group_ids': [(4, icit_group.id)]})
                return {'success': True, 'id': existing.id, 'message': 'Admin access granted to existing user.'}

            main_company = request.env['res.company'].sudo().search([], order='id asc', limit=1)
            new_user = users_model.create({
                'name': name,
                'login': email,
                'email': email,
                'password': password,
                'company_id': main_company.id,
                'company_ids': [(6, 0, [main_company.id])],
                'group_ids': [
                    (4, request.env.ref('base.group_user').id),
                    (4, icit_group.id),
                ],
            })
            return {'success': True, 'id': new_user.id}
        except AccessError as exc:
            return self._json_error(str(exc), status=403)
        except (ValidationError, ValueError) as exc:
            return self._json_error(str(exc), status=400)
        except Exception:
            _logger.exception('Failed to add admin user.')
            return self._json_error('Failed to add admin user.', status=500)

    @http.route('/admin/api/admins/remove', type='jsonrpc', auth='user', methods=['POST'], csrf=False)
    def remove_admin(self, **kwargs):
        try:
            self._check_icit_admin()
            user_id = int(kwargs.get('user_id') or 0)
            if not user_id:
                raise ValidationError('User ID is required.')

            current_uid = request.session.uid
            if user_id == current_uid:
                raise ValidationError('You cannot remove your own admin access.')

            user = request.env['res.users'].sudo().browse(user_id)
            if not user.exists():
                raise ValidationError('User not found.')

            icit_group = request.env.ref('saas_manager.group_icit_admin')
            user.write({'group_ids': [(3, icit_group.id)]})
            return {'success': True}
        except AccessError as exc:
            return self._json_error(str(exc), status=403)
        except (ValidationError, ValueError) as exc:
            return self._json_error(str(exc), status=400)
        except Exception:
            _logger.exception('Failed to remove admin user.')
            return self._json_error('Failed to remove admin user.', status=500)
