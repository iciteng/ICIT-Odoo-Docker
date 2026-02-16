import logging

from odoo.api import Environment

_logger = logging.getLogger(__name__)

# Static map for modules whose groups live under a different XML-ID prefix
# or have non-obvious naming conventions.
APP_GROUP_MAP = {
    'crm': [
        'sales_team.group_sale_salesman',
        'crm.group_crm_user',
    ],
    'sale_management': [
        'sales_team.group_sale_salesman',
        'sale.group_sale_order',
    ],
    'purchase': [
        'purchase.group_purchase_user',
    ],
    'stock': [
        'stock.group_stock_user',
    ],
    'account': [
        'account.group_account_invoice',
        'account.group_account_user',
    ],
    'hr': [
        'hr.group_hr_user',
    ],
    'project': [
        'project.group_project_user',
    ],
    'website': [
        'website.group_website_designer',
    ],
    'mrp': [
        'mrp.group_mrp_user',
    ],
    'hr_expense': [
        'hr_expense.group_hr_expense_team_approver',
    ],
    'hr_timesheet': [
        'hr_timesheet.group_hr_timesheet_user',
    ],
    'hr_holidays': [
        'hr_holidays.group_hr_holidays_user',
    ],
    'hr_recruitment': [
        'hr_recruitment.group_hr_recruitment_user',
    ],
    'fleet': [
        'fleet.fleet_group_user',
    ],
    'maintenance': [
        'maintenance.group_equipment_manager',
    ],
    'lunch': [
        'lunch.group_lunch_user',
    ],
}


def get_app_groups(env: Environment, module_name: str):
    """Return a ``res.groups`` recordset for every group belonging to *module_name*.

    Strategy:
    1. Check the static ``APP_GROUP_MAP`` for known hard-coded XML-IDs.
    2. Dynamically discover groups registered under ``ir.model.data`` for the module.
    """
    groups = env['res.groups']

    # 1. Static map
    for xmlid in APP_GROUP_MAP.get(module_name, []):
        grp = env.ref(xmlid, raise_if_not_found=False)
        if grp:
            groups |= grp

    # 2. Dynamic discovery via ir.model.data
    try:
        data_records = env['ir.model.data'].sudo().search([
            ('module', '=', module_name),
            ('model', '=', 'res.groups'),
        ])
        for rec in data_records:
            grp = env['res.groups'].browse(rec.res_id)
            if grp.exists():
                groups |= grp
    except Exception:
        _logger.warning(
            'Failed to discover groups dynamically for module %s',
            module_name,
            exc_info=True,
        )

    return groups
