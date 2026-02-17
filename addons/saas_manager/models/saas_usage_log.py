from datetime import datetime, time, timedelta

from odoo import fields, models


class SaasUsageLog(models.Model):
    _name = 'saas.usage.log'
    _description = 'SaaS Usage Log'

    tenant_id = fields.Many2one('saas.tenant', required=True, ondelete='cascade')
    date = fields.Date(required=True)
    active_users = fields.Integer(default=0)
    login_count = fields.Integer(default=0)
    storage_mb = fields.Float(default=0.0)

    def _day_bounds(self, day):
        start_dt = datetime.combine(day, time.min)
        end_dt = start_dt + timedelta(days=1)
        return start_dt, end_dt

    def _compute_login_count(self, company_id, day):
        start_dt, end_dt = self._day_bounds(day)
        self.env.cr.execute(
            """
            SELECT COUNT(*)
            FROM res_users_log l
            JOIN res_users u ON u.id = l.create_uid
            WHERE u.company_id = %s
              AND l.create_date >= %s
              AND l.create_date < %s
            """,
            (company_id, start_dt, end_dt),
        )
        row = self.env.cr.fetchone()
        return int(row[0] or 0) if row else 0

    def _compute_storage_mb(self, company_id):
        self.env.cr.execute(
            """
            SELECT COALESCE(SUM(file_size), 0)
            FROM ir_attachment
            WHERE company_id = %s
            """,
            (company_id,),
        )
        row = self.env.cr.fetchone()
        bytes_total = int(row[0] or 0) if row else 0
        return bytes_total / (1024.0 * 1024.0)

    def upsert_tenant_day(self, tenant, day=None):
        tenant = tenant.sudo()
        day = day or fields.Date.context_today(self)

        active_users = self.env['res.users'].sudo().search_count([
            ('company_id', '=', tenant.company_id.id),
            ('share', '=', False),
            ('active', '=', True),
        ])
        login_count = self._compute_login_count(tenant.company_id.id, day)
        storage_mb = self._compute_storage_mb(tenant.company_id.id)

        log = self.sudo().search([
            ('tenant_id', '=', tenant.id),
            ('date', '=', day),
        ], limit=1)
        vals = {
            'active_users': active_users,
            'login_count': login_count,
            'storage_mb': storage_mb,
        }
        if log:
            log.write(vals)
            return log
        vals.update({
            'tenant_id': tenant.id,
            'date': day,
        })
        return self.sudo().create(vals)

    def ensure_recent_for_tenant(self, tenant, days=30):
        tenant = tenant.sudo()
        today = fields.Date.context_today(self)
        for offset in range(days):
            day = today - timedelta(days=offset)
            self.upsert_tenant_day(tenant, day=day)

    def cron_collect_daily_usage(self):
        tenants = self.env['saas.tenant'].sudo().search([])
        today = fields.Date.context_today(self)
        for tenant in tenants:
            self.upsert_tenant_day(tenant, day=today)
