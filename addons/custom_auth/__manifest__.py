{
    'name': 'Custom Authentication',
    'version': '19.0.1.0.0',
    'category': 'Website',
    'summary': 'Custom login page with /admin backend access',
    'depends': ['web', 'saas_manager'],
    'data': [
        'views/login_templates.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
