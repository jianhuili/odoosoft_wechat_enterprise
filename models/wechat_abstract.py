
# coding=utf-8
from odoo import tools
from odoo import models, fields, api
from odoo.tools.translate import _

class WechatAbstract(models.AbstractModel):
    _name = 'wechat.enterprise.abstract'

    _description = 'Wechat Enterprise Abstract Model'

   
    def send(self):
        wechat_account_codes = self.env.context.get('wechat_account_code', [])
        users = self.env.context.get('message_users', '')
        user_ids = []
        if users:
            user_ids = users if isinstance(users, list) else [users]
        user_ids = filter(lambda a: a, user_ids)
        for code in wechat_account_codes:
            for obj in self:
                values = {
                    'obj': obj,
                    'content': self.env.context.get('message', ''),
                    'account_code': code,
                    'user_ids': user_ids,
                    'type': self.env.context.get('wechat_type', 'text'),
                    'template': self.env.context.get('wechat_template', ''),
                    'title': self.env.context.get('wechat_title', None),
                }

                self.env['odoo.wechat.enterprise.message'].create_message(**values)
