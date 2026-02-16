from odoo import fields, models


class SaasTenant(models.Model):
    _name = 'saas.tenant'
    _description = 'SaaS Tenant'

    name = fields.Char(required=True, string='Tenant Name')
    company_id = fields.Many2one('res.company', required=True, string='Company')
    status = fields.Selection(
        selection=[
            ('active', 'Active'),
            ('suspended', 'Suspended'),
            ('trial', 'Trial'),
        ],
        default='trial',
        required=True,
    )
    plan = fields.Selection(
        selection=[
            ('free', 'Free'),
            ('basic', 'Basic'),
            ('pro', 'Pro'),
            ('enterprise', 'Enterprise'),
        ],
        default='free',
        required=True,
    )
    max_users = fields.Integer(default=5, required=True)
    created_date = fields.Date(default=fields.Date.today, required=True)
    trial_end_date = fields.Date()
    allowed_app_ids = fields.Many2many('ir.module.module', string='Allowed Apps')
    admin_user_id = fields.Many2one('res.users', string='Admin User')

    def action_suspend(self):
        self.write({'status': 'suspended'})

    def action_activate(self):
        self.write({'status': 'active'})
