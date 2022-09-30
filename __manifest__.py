# -*- coding: utf-8 -*-
{
    'name': 'Odoosoft Wechat Enterprise Module',
    'version': '0.5',
    'category': 'odoosoft_wechat',
    'description': """
Odoosoft Wechat Enterprise""",
    'author': 'Matt Cai',
    'website': 'http://odoosoft.com',
    'depends': ['base', 'web'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',
        #'data/cron.xml',
        # 'views/wechat_settings_view.xml',
        'views/template_view.xml',
        'views/log_view.xml',
        'views/user_wizard_view.xml',
        'views/account_view.xml',
        'views/application_view.xml',
        'views/message_view.xml',
        'views/user_view.xml',
        'views/department_view.xml',
        'views/filter_view.xml',
        'views/app_map_view.xml',
        'views/menu.xml',
    ],
    'demo': [],
    "external_dependencies": {"python": ['wechatpy']},
    'application': True
}
