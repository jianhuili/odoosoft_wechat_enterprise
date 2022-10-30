# -*- coding: utf-8 -*-
{
    'name': 'Odoo Wechat Enterprise Module',
    'version': '0.5',
    'category': 'odoo_wechat',
    'description': """
Odoo Wechat Enterprise""",
    'author': 'Li Jianhui',
    'website': 'http://odoo.com',
    'depends': ['base', 'web'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',
        #'data/cron.xml',
        # 'views/wechat_settings_view.xml',
        'views/account_view.xml',
        'views/template_view.xml',
        'views/log_view.xml',
        'views/user_wizard_view.xml',
        'views/customer_view.xml',
        'views/message_view.xml',
        'views/customer_message_view.xml',
        'views/user_view.xml',
        'views/department_view.xml',
        'views/filter_view.xml',
        'views/menu.xml',
        'views/welcome_message_template_view.xml',
    ],
    'demo': [],
    "external_dependencies": {"python": ['wechatpy']},
    'application': True
}
