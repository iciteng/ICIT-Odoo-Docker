from odoo import fields, models


class SaasUsageLog(models.Model):
    _name = 'saas.usage.log'
    _description = 'SaaS Usage Log'

    tenant_id = fields.Many2one('saas.tenant', required=True, ondelete='cascade')
    date = fields.Date(required=True)
    active_users = fields.Integer(default=0)
    login_count = fields.Integer(default=0)
    storage_mb = fields.Float(default=0.0)
