{
    'name': 'SaaS Manager',
    'version': '19.0.1.0.0',
    'category': 'Administration',
    'depends': ['web', 'base'],
    'data': [
        'security/saas_security.xml',
        'security/ir.model.access.csv',
        'data/saas_data.xml',
        'views/dashboard_templates.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
