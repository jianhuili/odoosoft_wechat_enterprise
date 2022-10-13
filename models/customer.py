# coding=utf-8

import time
from odoo import tools
import logging
from odoo import models, fields, api, exceptions
from odoo.tools.translate import _
from wechatpy.enterprise import WeChatClient
from wechatpy.exceptions import WeChatClientException

_logger = logging.getLogger(__name__)


class WechatCustomer(models.Model):
    _name = 'odoo.wechat.enterprise.customer'
    _rec_name = 'external_userid'

    external_userid = fields.Char('External User ID', readonly=True,required=True)
    name = fields.Char('Name', readonly=True, required=True)
    avatar = fields.Char('Name', readonly=True)
    type = fields.Selection([('1', 'Wechat User'), ('2', 'Enterprise Wechat User')],'User Type', default='1', readonly=True)
    gender = fields.Selection([('0', 'Unknown'), ('1', 'Male'), ('1', 'Female')],'Gender', default='0', readonly=True)
    unionid = fields.Char('Union ID', readonly=True)
    position = fields.Char('Position', readonly=True)
    corp_name = fields.Char('Corp Name', readonly=True)
    corp_full_name = fields.Char('Corp Fullname', readonly=True)
    external_profile = fields.Char('Profile', readonly=True)
    mobile = fields.Char('Mobile')
    remark = fields.Char('Remark')
    unassigned_flag = fields.Boolean('Unassigned Flag', default=False)
    createtime = fields.Datetime('Createtime', readonly=True)

    follow_user = fields.Many2many('odoo.wechat.enterprise.user', 'wechat_enterprise_user_customer_rel', 'external_userid', 'wechat_userid',
                                   'Follow User')
    account = fields.Many2one('odoo.wechat.enterprise.account', 'Account', required=True, readonly=True)

    delete_flag = fields.Boolean('Delete Flag', default=False)

    def write(self, vals):
        # self.check_account_unique()
        self.env.cr.execute('SAVEPOINT wechat_write')
        result = super(WechatCustomer, self).write(vals)
        self.env.cr.execute('RELEASE SAVEPOINT wechat_write')
        return result

    @api.model
    def create(self, vals):
        self.env.cr.execute('SAVEPOINT wechat_customer_create')
        customer = super(WechatCustomer, self).create(vals)
        self.env.cr.execute('RELEASE SAVEPOINT wechat_customer_create')
        return customer


    def transfer(self, handover_userid, takeover_userid):
        """
        客户再分配

        :param handover_userid: 离职成员的userid
        :param takeover_userid: 接替成员的userid
        """

    def sync_wechat_server(self):
        """
        sync wechat server user info to local database
        """
        accounts = self.env['odoo.wechat.enterprise.account'].search([])
        for account in accounts:
            try:
                client = account.get_client()
                server_values = []
                # fetch customers of follow users
                customer_ids = self.get_id_list(client)
                for customer_id in customer_ids:
                    customer_info = client.external_contact.get(customer_id)
                    customer_info['unassigned_flag'] = False
                    server_values.append(customer_info)

                # fetch all unassigned customers
                unsigned_customer_ids = self.get_unassigned_id_list(client)
                # get customer detail info
                for customer_id in unsigned_customer_ids:
                    customer_info = client.external_contact.get(customer_id)
                    customer_info['unassigned_flag'] = True
                    server_values.append(customer_info)

                # get local customers
                local_values = {v['external_userid']: v for v in self.search_read([('account', '=', account.id)],
                                                                        ['name', 'avatar', 'type', 'gender', 'position', 'corp_name', 'corp_full_name', 'follow_user'])}
                ## 检查并更新本地客户信息
                for server_value in server_values:
                    # if someone on server and in local
                    if server_value['external_userid'] in local_values:
                        external_user_id = server_value['external_userid']
                        temp_server_value = {
                            'name':  server_value['name'],
                            'avatar': server_value['avatar'],
                            'type': str(server_value['type']),
                            'gender': str(server_value['gender']),
                            'position': server_value['position'],
                            'corp_name': server_value['corp_name'],
                            'corp_full_name': server_value['corp_full_name'],
                            'unassigned_flag': server_value['unassigned_flag'],
                            'follow_user_id': [v['userid'] for v in server_value['follow_user']]
                        }
                        local_value = local_values[external_user_id]
                        temp_local_value = {
                            'name': local_value['name'],
                            'avatar': local_value['avatar'],
                            'type': local_value['type'],
                            'gender': local_value['gender'],
                            'position': local_value['position'],
                            'corp_name': local_value['corp_name'],
                            'corp_full_name': local_value['corp_full_name'],
                            'unassigned_flag': local_value['unassigned_flag'],
                            'follow_user_id': [v['user_code'] for v in local_value['unassigned_flag']],
                        }
                        # if have difference
                        if set(temp_server_value.items()) - set(temp_local_value.items()):
                            # update follow user
                            temp_server_value['follow_user'] = self.get_wechat_users(account.id,temp_server_value['follow_user_id'] )
                            self.env['odoo.wechat.enterprise.customer'].browse(local_value['id']).write(temp_server_value)
                        
                        # un registry local value
                        del local_values[external_user_id]

                    # if someone on server but not in local
                    else:
                        _logger.info('Add missing server customer:%s', server_value['userid'])
                        # self.env['odoo.wechat.enterprise.log'].log_info(u'同步服务器用户', u'服务器用户:%s没有在本机找到对应关系' % server_value['userid'])
                        self.env['odoo.wechat.enterprise.log'].log_info(u'同步服务器用户', u'添加本地不存在用户:%s' % server_value['userid'])

                        new_server_value = {
                            'name':  server_value['name'],
                            'avatar': server_value['avatar'],
                            'type': str(server_value['type']),
                            'gender': str(server_value['gender']),
                            'position': server_value['position'],
                            'corp_name': server_value['corp_name'],
                            'corp_full_name': server_value['corp_full_name'],
                            'unassigned_flag': server_value['unassigned_flag'],
                            'follow_user_id': [v['userid'] for v in server_value['follow_user']]
                        }
                        new_server_value['follow_user'] = self.get_wechat_users(account.id,temp_server_value['follow_user_id'] )

                        self.env['odoo.wechat.enterprise.customer'].create(new_server_value)

                # delete customer on local but not on server
                if local_values:
                    mismatch_ids = [v['id'] for v in local_values.values()]
                    self.browse(mismatch_ids).write({'delete_flag': True})

            except WeChatClientException as e:
                _logger.error('Get error in sync from server', e)
                self.env['odoo.wechat.enterprise.log'].log_info(u'同步服务器用户', str(e))
        self.env['odoo.wechat.enterprise.log'].log_info(u'同步服务器用户', u'同步完成')

    def get_wechat_users(self, account_id, wechat_user_ids):
        """
        获取Follow企业微信用户
        """
        users = self.env['odoo.wechat.enterprise.user'].search_read([('account', '=', account_id),('user_code', 'in', wechat_user_ids)])

        return users

    @staticmethod
    def get_unassigned_id_list(wechat_client):
        """
        获取离职成员的客户列表
        """
        unassigned_customer_ids =[]
        page_id = 0
        result_count = 1000
        while(result_count >= 1000):
            customer_ids = wechat_client.external_contact.get_unassigned_list(page_id, 1000)
            unassigned_customer_ids.extend(customer_ids)
            result_count = len(customer_ids)
            page_id +=1
  
    @staticmethod
    def get_id_list(wechat_client):
        """
        获取客户ID列表
        """
       # get follow users
        follow_users = wechat_client.external_contact.get_follow_user_list()
        all_customer_ids = []
        # fetch customers of follow users
        for user in follow_users:
            # get external customer id list
            customer_ids = wechat_client.external_contact.list(user.userid)
            all_customer_ids.extend(customer_ids)

   