import json
import logging
import re
import hashlib
import hmac
import time
import base64

import odoo.api
import odoo.service.db
import odoo.tools.config
from odoo import http
from odoo.http import request, Response
from odoo.modules.registry import Registry
from odoo.addons.web.controllers.database import DBNAME_PATTERN

from ..utils import is_admin_subdomain
from ..allowlist import get_db_allowlist, set_db_allowlist, is_module_allowed

_logger = logging.getLogger(__name__)
MODULE_NAME_PATTERN = r'^[a-zA-Z][a-zA-Z0-9_]+$'


class AppsController(http.Controller):
    def _guard(self):
        if not is_admin_subdomain():
            return Response(
                json.dumps({'success': False, 'error': 'Not found'}),
                status=404,
                content_type='application/json',
            )
        return None

    def _validate_dbname(self, dbname):
        if not dbname or not re.match(DBNAME_PATTERN, dbname):
            return Response(
                json.dumps({'success': False, 'error': 'Invalid database name'}),
                status=400,
                content_type='application/json',
            )

        if dbname not in http.db_list():
            return Response(
                json.dumps({'success': False, 'error': 'Database not found'}),
                status=404,
                content_type='application/json',
            )

        return None

    def _get_token_secret(self):
        admin_pwd = odoo.tools.config.get('admin_passwd', '')
        return hashlib.sha256(('icit_saas_guard_' + admin_pwd).encode()).digest()

    def _create_auth_token(self):
        expires = int(time.time()) + 1800
        payload = str(expires)
        secret = self._get_token_secret()
        sig = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
        token = base64.b64encode((payload + ':' + sig).encode()).decode()
        return token

    def _verify_auth_token(self, token):
        try:
            decoded = base64.b64decode(token).decode()
            payload, sig = decoded.split(':', 1)
            secret = self._get_token_secret()
            expected_sig = hmac.new(
                secret, payload.encode(), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(expected_sig, sig):
                return False
            expires = int(payload)
            if expires < int(time.time()):
                return False
            return True
        except Exception:
            return False

    def _require_token(self):
        token = request.httprequest.headers.get('X-Apps-Token')
        if not token or not self._verify_auth_token(token):
            return Response(
                json.dumps(
                    {'success': False, 'error': 'Missing or invalid apps token'}
                ),
                status=401,
                content_type='application/json',
            )
        return None

    def _validate_module_name(self, name):
        if not name or not re.match(MODULE_NAME_PATTERN, name):
            return Response(
                json.dumps({'success': False, 'error': 'Invalid module name'}),
                status=400,
                content_type='application/json',
            )
        return None

    @http.route(
        '/web/database/apps/auth',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def apps_auth(self, **kwargs):
        blocked = self._guard()
        if blocked:
            return blocked

        try:
            payload = json.loads(request.httprequest.data or b'{}')
            master_pwd = payload.get('master_pwd')
        except Exception as e:
            _logger.exception('Failed to parse auth payload')
            return Response(
                json.dumps({'success': False, 'error': str(e)}),
                status=400,
                content_type='application/json',
            )

        try:
            if not odoo.service.db.check_super(master_pwd):
                return Response(
                    json.dumps(
                        {'success': False, 'error': 'Invalid master password'}
                    ),
                    status=403,
                    content_type='application/json',
                )
            token = self._create_auth_token()
            return Response(
                json.dumps({'success': True, 'data': {'token': token}}),
                content_type='application/json',
            )
        except Exception as e:
            _logger.exception('Failed to authenticate apps request')
            return Response(
                json.dumps({'success': False, 'error': str(e)}),
                status=500,
                content_type='application/json',
            )

    @http.route(
        '/web/database/apps/install',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def apps_install(self, **kwargs):
        blocked = self._guard()
        if blocked:
            return blocked

        invalid_token = self._require_token()
        if invalid_token:
            return invalid_token

        dbname = None
        try:
            payload = json.loads(request.httprequest.data or b'{}')
            dbname = payload.get('dbname')
            module_name = payload.get('module_name')
            module_names = payload.get('module_names')

            if module_name and module_names is None:
                module_names = [module_name]

            if module_names is None:
                module_names = []

            if not isinstance(module_names, list):
                return Response(
                    json.dumps(
                        {'success': False, 'error': 'module_names must be an array'}
                    ),
                    status=400,
                    content_type='application/json',
                )

            invalid = self._validate_dbname(dbname)
            if invalid:
                return invalid

            for module in module_names:
                if not isinstance(module, str):
                    return Response(
                        json.dumps(
                            {
                                'success': False,
                                'error': 'module_names entries must be strings',
                            }
                        ),
                        status=400,
                        content_type='application/json',
                    )
                invalid_module_name = self._validate_module_name(module)
                if invalid_module_name:
                    return invalid_module_name

            for name in module_names:
                if not is_module_allowed(dbname, name):
                    return Response(
                        json.dumps(
                            {
                                'success': False,
                                'error': 'Module blocked by allowlist: ' + name,
                            }
                        ),
                        status=403,
                        content_type='application/json',
                    )

            with Registry(dbname).cursor() as cr:
                env = odoo.api.Environment(cr, odoo.api.SUPERUSER_ID, {})
                for module in module_names:
                    module_rec = env['ir.module.module'].search(
                        [('name', '=', module)],
                        limit=1,
                    )
                    if not module_rec:
                        return Response(
                            json.dumps(
                                {
                                    'success': False,
                                    'error': "Module not found: %s" % module,
                                }
                            ),
                            status=404,
                            content_type='application/json',
                        )
                    module_rec.button_install()
                    cr.commit()

            Registry.new(dbname, update_module=True)
            return Response(
                json.dumps({'success': True}),
                content_type='application/json',
            )
        except Exception as e:
            _logger.exception("Failed to install apps for database '%s'", dbname)
            return Response(
                json.dumps({'success': False, 'error': str(e)}),
                status=500,
                content_type='application/json',
            )

    @http.route(
        '/web/database/apps/uninstall',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def apps_uninstall(self, **kwargs):
        blocked = self._guard()
        if blocked:
            return blocked

        invalid_token = self._require_token()
        if invalid_token:
            return invalid_token

        dbname = None
        try:
            payload = json.loads(request.httprequest.data or b'{}')
            dbname = payload.get('dbname')
            module_name = payload.get('module_name')
            module_names = payload.get('module_names')

            if module_name and module_names is None:
                module_names = [module_name]

            if module_names is None:
                module_names = []

            if not isinstance(module_names, list):
                return Response(
                    json.dumps(
                        {'success': False, 'error': 'module_names must be an array'}
                    ),
                    status=400,
                    content_type='application/json',
                )

            invalid = self._validate_dbname(dbname)
            if invalid:
                return invalid

            for module in module_names:
                if not isinstance(module, str):
                    return Response(
                        json.dumps(
                            {
                                'success': False,
                                'error': 'module_names entries must be strings',
                            }
                        ),
                        status=400,
                        content_type='application/json',
                    )
                invalid_module_name = self._validate_module_name(module)
                if invalid_module_name:
                    return invalid_module_name

            with Registry(dbname).cursor() as cr:
                env = odoo.api.Environment(cr, odoo.api.SUPERUSER_ID, {})
                for module in module_names:
                    module_rec = env['ir.module.module'].search(
                        [('name', '=', module)],
                        limit=1,
                    )
                    if not module_rec:
                        return Response(
                            json.dumps(
                                {
                                    'success': False,
                                    'error': "Module not found: %s" % module,
                                }
                            ),
                            status=404,
                            content_type='application/json',
                        )
                    module_rec.button_uninstall()
                    cr.commit()

            Registry.new(dbname, update_module=True)
            return Response(
                json.dumps({'success': True}),
                content_type='application/json',
            )
        except Exception as e:
            _logger.exception("Failed to uninstall apps for database '%s'", dbname)
            return Response(
                json.dumps({'success': False, 'error': str(e)}),
                status=500,
                content_type='application/json',
            )

    @http.route(
        '/web/database/apps/upgrade',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def apps_upgrade(self, **kwargs):
        blocked = self._guard()
        if blocked:
            return blocked

        invalid_token = self._require_token()
        if invalid_token:
            return invalid_token

        dbname = None
        try:
            payload = json.loads(request.httprequest.data or b'{}')
            dbname = payload.get('dbname')
            module_name = payload.get('module_name')
            module_names = payload.get('module_names')

            if module_name and module_names is None:
                module_names = [module_name]

            if module_names is None:
                module_names = []

            if not isinstance(module_names, list):
                return Response(
                    json.dumps(
                        {'success': False, 'error': 'module_names must be an array'}
                    ),
                    status=400,
                    content_type='application/json',
                )

            invalid = self._validate_dbname(dbname)
            if invalid:
                return invalid

            for module in module_names:
                if not isinstance(module, str):
                    return Response(
                        json.dumps(
                            {
                                'success': False,
                                'error': 'module_names entries must be strings',
                            }
                        ),
                        status=400,
                        content_type='application/json',
                    )
                invalid_module_name = self._validate_module_name(module)
                if invalid_module_name:
                    return invalid_module_name

            with Registry(dbname).cursor() as cr:
                env = odoo.api.Environment(cr, odoo.api.SUPERUSER_ID, {})
                for module in module_names:
                    module_rec = env['ir.module.module'].search(
                        [('name', '=', module)],
                        limit=1,
                    )
                    if not module_rec:
                        return Response(
                            json.dumps(
                                {
                                    'success': False,
                                    'error': "Module not found: %s" % module,
                                }
                            ),
                            status=404,
                            content_type='application/json',
                        )
                    module_rec.button_upgrade()
                    cr.commit()

            Registry.new(dbname, update_module=True)
            return Response(
                json.dumps({'success': True}),
                content_type='application/json',
            )
        except Exception as e:
            _logger.exception("Failed to upgrade apps for database '%s'", dbname)
            return Response(
                json.dumps({'success': False, 'error': str(e)}),
                status=500,
                content_type='application/json',
            )

    @http.route(
        '/web/database/apps/allowlist/<dbname>',
        type='http',
        auth='none',
        methods=['GET'],
    )
    def apps_allowlist_get(self, dbname, **kwargs):
        blocked = self._guard()
        if blocked:
            return blocked

        invalid = self._validate_dbname(dbname)
        if invalid:
            return invalid

        try:
            config = get_db_allowlist(dbname)
            return Response(
                json.dumps({'success': True, 'data': config}),
                content_type='application/json',
            )
        except Exception as e:
            _logger.exception(
                "Failed to retrieve allowlist for database '%s'", dbname
            )
            return Response(
                json.dumps({'success': False, 'error': str(e)}),
                status=500,
                content_type='application/json',
            )

    @http.route(
        '/web/database/apps/allowlist/<dbname>',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def apps_allowlist_set(self, dbname, **kwargs):
        blocked = self._guard()
        if blocked:
            return blocked

        invalid_token = self._require_token()
        if invalid_token:
            return invalid_token

        invalid = self._validate_dbname(dbname)
        if invalid:
            return invalid

        try:
            body_data = json.loads(request.httprequest.data or b'{}')
            mode = body_data.get('mode')
            if mode not in ('allowlist', 'denylist', 'disabled'):
                return Response(
                    json.dumps({'success': False, 'error': 'Invalid allowlist mode'}),
                    status=400,
                    content_type='application/json',
                )
            set_db_allowlist(dbname, body_data)
            return Response(
                json.dumps({'success': True}),
                content_type='application/json',
            )
        except ValueError as e:
            return Response(
                json.dumps({'success': False, 'error': str(e)}),
                status=400,
                content_type='application/json',
            )
        except Exception as e:
            _logger.exception("Failed to set allowlist for database '%s'", dbname)
            return Response(
                json.dumps({'success': False, 'error': str(e)}),
                status=500,
                content_type='application/json',
            )

    @http.route(
        '/web/database/apps/status/<dbname>',
        type='http',
        auth='none',
        methods=['GET'],
    )
    def apps_status(self, dbname, **kwargs):
        blocked = self._guard()
        if blocked:
            return blocked

        invalid = self._validate_dbname(dbname)
        if invalid:
            return invalid

        module_name = request.params.get('module')
        invalid_module_name = self._validate_module_name(module_name)
        if invalid_module_name:
            return invalid_module_name

        try:
            with Registry(dbname).cursor() as cr:
                env = odoo.api.Environment(cr, odoo.api.SUPERUSER_ID, {})
                module = env['ir.module.module'].search(
                    [('name', '=', module_name)],
                    limit=1,
                )
                if not module:
                    return Response(
                        json.dumps({'success': False, 'error': 'Module not found'}),
                        status=404,
                        content_type='application/json',
                    )
                data = {'state': module.state, 'name': module.name}
        except Exception as e:
            _logger.exception(
                "Failed to retrieve module status for database '%s'", dbname
            )
            return Response(
                json.dumps({'success': False, 'error': str(e)}),
                status=500,
                content_type='application/json',
            )

        return Response(
            json.dumps({'success': True, 'data': data}),
            content_type='application/json',
        )

    @http.route(
        '/web/database/apps/list/<dbname>',
        type='http',
        auth='none',
        methods=['GET'],
    )
    def apps_list(self, dbname, **kwargs):
        blocked = self._guard()
        if blocked:
            return blocked

        invalid = self._validate_dbname(dbname)
        if invalid:
            return invalid

        try:
            with Registry(dbname).cursor() as cr:
                env = odoo.api.Environment(cr, odoo.api.SUPERUSER_ID, {})
                modules = env['ir.module.module'].search_read(
                    [],
                    fields=[
                        'name',
                        'shortdesc',
                        'summary',
                        'state',
                        'application',
                        'category_id',
                        'author',
                        'installed_version',
                    ],
                    order='category_id, shortdesc',
                )
                categories = env['ir.module.category'].search_read(
                    [],
                    fields=['id', 'name', 'parent_id'],
                    order='name',
                )
                al_config = get_db_allowlist(dbname)
                for m in modules:
                    m['_blocked'] = not is_module_allowed(dbname, m['name'])
        except Exception as e:
            _logger.exception("Failed to list apps for database '%s'", dbname)
            return Response(
                json.dumps({'success': False, 'error': str(e)}),
                status=500,
                content_type='application/json',
            )

        return Response(
            json.dumps(
                {
                    'success': True,
                    'data': {
                        'modules': modules,
                        'categories': categories,
                        'allowlist': al_config,
                    },
                }
            ),
            content_type='application/json',
        )
