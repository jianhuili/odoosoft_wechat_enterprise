# coding=utf-8

from odoo import tools
from odoo import models, fields, api
from odoo.tools.translate import _

class WechatFilterErrorLog(models.Model):
    _name = 'odoo.wechat.enterprise.log'
    _order = 'create_date desc'

    name = fields.Char('Name')
    message = fields.Char('Message')
    create_date = fields.Datetime('Create Datetime')

    @api.model
    def log_info(self, name, message):
        self.sudo().create({'name': name, 'message': message})
