from odoo import fields, models


class SaasAppAccess(models.Model):
    _name = 'saas.app.access'
    _description = 'SaaS App Access'

    tenant_id = fields.Many2one('saas.tenant', required=True, ondelete='cascade')
    module_id = fields.Many2one('ir.module.module', required=True, ondelete='cascade')
    enabled = fields.Boolean(default=False)
