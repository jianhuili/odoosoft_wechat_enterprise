
# coding=utf-8
from odoo import tools
from odoo import models, fields, api
from odoo.tools.translate import _
from wechatpy.enterprise import WeChatClient

class WechatAccount(models.Model):
    _name = 'odoo.wechat.enterprise.account'
    code = fields.Char('Company Code', required=True)
    name = fields.Char('Company Name', required=True)
    corpid = fields.Char('CorpID', required=True)
    agentid = fields.Char('AgentId', required=True)
    app_secret = fields.Char('App Secret', required=True)
    address_secret = fields.Char('AddressBook Secret', required=True)
    token = fields.Char('Callback Token', required=True)
    ase_key = fields.Char('EncodingAESKey', required=True)
    remark = fields.Char('Remark')
    callback_url = fields.Char(string='Callback URL', compute='_compute_url')
    _sql_constraints = [('wechat_account_code_unique', 'unique(code)', _('Code must be unique !'))]

    @api.model
    @tools.ormcache(skiparg=3)
    def get_client_by_code(self, name):
        account = self.search([('name', '=', name)])
        if account:
            return WeChatClient(account.corpid, account.app_secret)
        else:
            return None

    @tools.ormcache()
    def get_client(self):
        return WeChatClient(self.corpid, self.app_secret)

    def _compute_url(self):
        address = self.env['ir.config_parameter'].get_param('wechat.base.url')
        for account in self:
            account.callback_url = '%s/wechat_enterprise/%s/api' % (address, account.code)

    def process_request(self, msg):
        # find match filter
        # if msg.type == 'event':
        #     match_filters = self.filters.search(
        #         [('type', '=', 'event'), ('event_type', '=', msg.event), ('active', '=', True), ('is_template', '=', False)])
        # else:
        #     match_filters = self.filters.search([('type', '=', msg.type), ('active', '=', True), ('is_template', '=', False)])

        # for a_filter in match_filters:
        #     result = a_filter.process(msg)
        #     if result[0]:
        #         return result[1]
        # else:
        #     return None
        None
