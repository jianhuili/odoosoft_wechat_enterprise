
# coding=utf-8
from odoo import tools
from odoo import models, fields, api
from odoo.tools.translate import _

class DbConfigSettings(models.TransientModel):
    _name = 'odoo.wechat.config.settings'
    _inherit = 'res.config.settings'

    default_account = fields.Many2one('odoo.wechat.enterprise.account', 'Default User Page Account Value', default_model='odoo.wechat.enterprise.user')