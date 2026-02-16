import logging

from odoo import models

from .app_group_mapping import get_app_groups

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _assign_tenant_app_groups(self):
        """Add groups for every enabled app on the user's tenant."""
        for user in self:
            tenant = self.env['saas.tenant'].sudo().search(
                [('company_id', '=', user.company_id.id)], limit=1,
            )
            if not tenant or not tenant.allowed_app_ids:
                continue

            groups_to_add = self.env['res.groups']
            for module in tenant.allowed_app_ids:
                groups_to_add |= get_app_groups(self.env, module.name)

            if groups_to_add:
                user.sudo().write({
                    'groups_id': [(4, g.id) for g in groups_to_add],
                })

    def _strip_admin_groups(self):
        """Remove system/erp-manager groups so tenant users can never self-admin."""
        dangerous_groups = [
            self.env.ref('base.group_system', raise_if_not_found=False),
            self.env.ref('base.group_erp_manager', raise_if_not_found=False),
        ]
        ids_to_remove = [g.id for g in dangerous_groups if g]
        if not ids_to_remove:
            return
        for user in self:
            user.sudo().write({
                'groups_id': [(3, gid) for gid in ids_to_remove],
            })

    @classmethod
    def _is_tenant_company(cls, env, company_id):
        """Return True when *company_id* belongs to a SaaS tenant."""
        return bool(
            env['saas.tenant'].sudo().search_count(
                [('company_id', '=', company_id)],
            )
        )

    def create(self, vals_list):
        """Override to auto-assign tenant app groups and strip admin groups."""
        # Support both single-dict and list-of-dicts (Odoo 17+ uses list)
        single = isinstance(vals_list, dict)
        if single:
            vals_list = [vals_list]

        users = super().create(vals_list)

        for user in users:
            if not self._is_tenant_company(self.env, user.company_id.id):
                continue
            user._strip_admin_groups()
            user._assign_tenant_app_groups()

        return users[0] if single and len(users) == 1 else users
