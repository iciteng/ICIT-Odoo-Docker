import logging
from collections import defaultdict
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

    def _is_icit_email(self, email):
        return bool((email or '').strip().lower().endswith('@icitsolutions.com'))

    def _main_company(self):
        company = request.env['res.company'].sudo().search([], order='id asc', limit=1)
        if not company:
            raise ValidationError('Main company was not found.')
        return company

    def _icit_admin_group_ids(self):
        """Groups every admin-portal ICIT admin must have."""
        group_xmlids = [
            'saas_manager.group_icit_admin',
            'base.group_user',
            'base.group_multi_company',
            'base.group_erp_manager',
        ]
        group_ids = []
        for xmlid in group_xmlids:
            group = request.env.ref(xmlid, raise_if_not_found=False)
            if group:
                group_ids.append(group.id)
        return group_ids

    def _dependency_roots(self, root_modules):
        """Map dependency module name -> set of enabled root module names that require it."""
        deps_model = request.env['ir.module.module.dependency'].sudo()
        dep_map = defaultdict(list)
        for dep in deps_model.search([]):
            module_name = dep.module_id.name
            if module_name and dep.name:
                dep_map[module_name].append(dep.name)

        to_visit = []
        seen_pairs = set()
        roots_by_dep = defaultdict(set)

        for root in root_modules:
            to_visit.append((root.name, root.name))

        while to_visit:
            current_name, root_name = to_visit.pop()
            for dep_name in dep_map.get(current_name, []):
                pair = (dep_name, root_name)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

                roots_by_dep[dep_name].add(root_name)
                to_visit.append((dep_name, root_name))

        return roots_by_dep

    @http.route('/admin/api/stats', type='jsonrpc', auth='user', methods=['POST'], csrf=False)
    def get_stats(self, **kwargs):
        try:
            self._check_icit_admin()
            tenant_model = request.env['saas.tenant'].sudo()
            usage_model = request.env['saas.usage.log'].sudo()
            users_model = request.env['res.users'].sudo()

            tenants = tenant_model.search([])
            total_tenants = len(tenants)
            company_ids = tenants.mapped('company_id').ids
            total_users = users_model.search_count([
                ('company_id', 'in', company_ids),
                ('share', '=', False),
                ('active', '=', True),
            ]) if company_ids else 0

            today = fields.Date.today()
            for tenant in tenants:
                usage_model.upsert_tenant_day(tenant, day=today)

            today_logs = usage_model.search([
                ('tenant_id', 'in', tenants.ids),
                ('date', '=', today),
            ])
            active_today = int(sum(today_logs.mapped('login_count')))
            if active_today == 0:
                active_today = int(sum(today_logs.mapped('active_users')))
            storage_mb = float(sum(today_logs.mapped('storage_mb')))
            if storage_mb <= 0:
                request.env.cr.execute("SELECT pg_database_size(current_database())")
                row = request.env.cr.fetchone()
                storage_mb = float((row[0] or 0) / (1024.0 * 1024.0)) if row else 0.0

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
            admin_email = (kwargs.get('admin_email') or '').strip().lower()
            admin_name = (kwargs.get('admin_name') or '').strip()
            admin_password = (kwargs.get('admin_password') or '').strip()
            plan = (kwargs.get('plan') or 'free').strip().lower()
            max_users = int(kwargs.get('max_users') or 5)
            allowed_plans = {'free', 'basic', 'pro', 'enterprise'}

            if not company_name or not admin_email or not admin_name:
                raise ValidationError('Company name, admin email, and admin name are required.')
            if not admin_password:
                raise ValidationError('Admin password is required.')
            if self._is_icit_email(admin_email):
                raise ValidationError('ICIT emails are reserved for platform admins. Use a tenant email.')
            if plan == 'trial':
                plan = 'free'
            if plan not in allowed_plans:
                raise ValidationError('Invalid plan value.')
            if max_users < 1:
                raise ValidationError('Max users must be at least 1.')
            existing_user = request.env['res.users'].sudo().search([('login', '=ilike', admin_email)], limit=1)
            if existing_user:
                company_name = existing_user.company_id.name if existing_user.company_id else 'Unknown'
                raise ValidationError(f'A user with this email already exists in "{company_name}".')

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
                        if self._is_icit_email(admin_email):
                            raise ValidationError('ICIT emails are reserved for platform admins.')
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
            items = [{
                'id': user.id,
                'name': user.name or '',
                'login': user.login or '',
            } for user in users]
            return {'users': items}
        except AccessError as exc:
            return self._json_error(str(exc), status=403)
        except Exception:
            _logger.exception('Failed to fetch users for SaaS tenant %s.', tenant_id)
            return self._json_error('Failed to fetch tenant users.', status=500)

    @http.route('/admin/api/tenants/<int:tenant_id>/users/add', type='jsonrpc', auth='user', methods=['POST'], csrf=False)
    def add_tenant_user(self, tenant_id, **kwargs):
        try:
            self._check_icit_admin()
            tenant = request.env['saas.tenant'].sudo().browse(tenant_id)
            if not tenant.exists():
                return self._json_error('Tenant not found.', status=404)

            name = (kwargs.get('name') or '').strip()
            email = (kwargs.get('email') or '').strip().lower()
            password = (kwargs.get('password') or '').strip()

            if not name or not email or not password:
                raise ValidationError('Name, email, and password are required.')
            if self._is_icit_email(email):
                raise ValidationError('ICIT emails must be added in Admin Users and remain in the ICIT company.')

            existing = request.env['res.users'].sudo().search([('login', '=ilike', email)], limit=1)
            if existing:
                if existing.company_id and existing.company_id.id == tenant.company_id.id:
                    return {
                        'success': True,
                        'id': existing.id,
                        'message': 'User already exists in this company.',
                    }
                company_name = existing.company_id.name if existing.company_id else 'Unknown'
                raise ValidationError(f'A user with this email already exists in "{company_name}".')

            active_users = request.env['res.users'].sudo().search_count([
                ('company_id', '=', tenant.company_id.id),
                ('share', '=', False),
                ('active', '=', True),
            ])
            if tenant.max_users and active_users >= tenant.max_users:
                raise ValidationError('User limit reached for this company.')

            user = request.env['res.users'].sudo().create({
                'name': name,
                'login': email,
                'email': email,
                'password': password,
                'company_id': tenant.company_id.id,
                'company_ids': [(6, 0, [tenant.company_id.id])],
                'group_ids': [(4, request.env.ref('base.group_user').id)],
            })
            return {'success': True, 'id': user.id}
        except AccessError as exc:
            return self._json_error(str(exc), status=403)
        except (ValidationError, ValueError) as exc:
            return self._json_error(str(exc), status=400)
        except Exception:
            _logger.exception('Failed to add user for SaaS tenant %s.', tenant_id)
            return self._json_error('Failed to add user.', status=500)

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

            explicit_enabled = tenant.allowed_app_ids
            explicit_enabled_ids = set(explicit_enabled.ids)
            dependency_roots = self._dependency_roots(explicit_enabled)

            app_label_by_name = {
                mod.name: (mod.shortdesc or mod.name)
                for mod in all_apps
            }

            apps = []
            for mod in all_apps:
                required_by_names = sorted(dependency_roots.get(mod.name, set()))
                required_by_labels = [app_label_by_name.get(name, name) for name in required_by_names]
                is_dependency_required = bool(required_by_names)
                explicit = mod.id in explicit_enabled_ids

                apps.append({
                    'id': mod.id,
                    'name': mod.shortdesc or mod.name,
                    'technical_name': mod.name,
                    'enabled': explicit or is_dependency_required,
                    'locked': is_dependency_required,
                    'required_by': required_by_labels,
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
                        user.write({'group_ids': group_cmds})

                tenant.write({'allowed_app_ids': [(4, module.id)]})
            else:
                explicit_enabled = tenant.allowed_app_ids
                roots_source = explicit_enabled - module if module in explicit_enabled else explicit_enabled
                dependency_roots = self._dependency_roots(roots_source)
                required_by_names = sorted(dependency_roots.get(module.name, set()))
                if required_by_names:
                    labels = request.env['ir.module.module'].sudo().search([
                        ('name', 'in', required_by_names),
                    ])
                    label_by_name = {m.name: (m.shortdesc or m.name) for m in labels}
                    required_by = ', '.join(label_by_name.get(name, name) for name in required_by_names)
                    return self._json_error(
                        f'Cannot disable this app because it is required by: {required_by}.',
                        status=409,
                    )

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
                        user.write({'group_ids': group_cmds})

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

            usage_model = request.env['saas.usage.log'].sudo()
            usage_model.ensure_recent_for_tenant(tenant, days=30)
            start_date = fields.Date.today() - timedelta(days=29)
            logs = usage_model.search(
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
            required_group_ids = self._icit_admin_group_ids()
            main_company = self._main_company()

            if existing:
                if icit_group.id in existing.group_ids.ids:
                    raise ValidationError('User already has admin access.')
                existing.write({
                    'company_id': main_company.id,
                    'company_ids': [(6, 0, [main_company.id])],
                    'group_ids': [(4, gid) for gid in required_group_ids],
                })
                return {'success': True, 'id': existing.id, 'message': 'Admin access granted to existing user.'}

            new_user = users_model.create({
                'name': name,
                'login': email,
                'email': email,
                'password': password,
                'company_id': main_company.id,
                'company_ids': [(6, 0, [main_company.id])],
                'group_ids': [(4, gid) for gid in required_group_ids],
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
            groups_to_remove = [icit_group.id]
            erp_group = request.env.ref('base.group_erp_manager', raise_if_not_found=False)
            if erp_group:
                groups_to_remove.append(erp_group.id)
            user.write({'group_ids': [(3, gid) for gid in groups_to_remove]})
            return {'success': True}
        except AccessError as exc:
            return self._json_error(str(exc), status=403)
        except (ValidationError, ValueError) as exc:
            return self._json_error(str(exc), status=400)
        except Exception:
            _logger.exception('Failed to remove admin user.')
            return self._json_error('Failed to remove admin user.', status=500)
