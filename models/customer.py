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

    external_userid = fields.Char('External User ID', readonly=True)
    name = fields.Char('Name', readonly=True)
    avatar = fields.Char('Name', readonly=True)
    type = fields.Selection([('1', 'Wechat User'), ('2', 'Enterprise Wechat User')],'User Type', default='1', readonly=True)
    gender = fields.Selection([('0', 'Unknown'), ('1', 'Male'), ('2', 'Female')],'Gender', default='0', readonly=True)
    unionid = fields.Char('Union ID', readonly=True)
    corp_name = fields.Char('Corp Name', readonly=True)
    corp_full_name = fields.Char('Corp Fullname', readonly=True)
    external_profile = fields.Char('Profile', readonly=True)
    mobile = fields.Char('Mobile')
    remark = fields.Char('Remark')
    unassigned_flag = fields.Boolean('Unassigned Flag', default=False)

    createtime = fields.Datetime('Createtime', readonly=True)
    follow_userid = fields.Char('Follow UserID')

    # follow_user = fields.Many2many('odoo.wechat.enterprise.user', 'wechat_enterprise_user_customer_rel', 'external_userid', 'wechat_userid',
    #                                'Follow User')
    account = fields.Many2one('odoo.wechat.enterprise.account', 'Account', readonly=True)

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

        _logger.info(u'Sync wechat server customer data-%s', u'Start')
        accounts = self.env['odoo.wechat.enterprise.account'].search([])
        for account in accounts:
            try:
                client = account.get_client()
                
                # get local customers
                local_values = {v['external_userid']: v for v in self.search_read([('account', '=', account.id)],
                                                                        ['external_userid','name', 'avatar', 'type', 'gender','corp_name', 'corp_full_name', 'follow_userid','unassigned_flag'])}
 
                # fetch all customers
                customer_id_infos = self.get_customer_id_list(client)
   
                for customer_id_info in customer_id_infos:
                    external_userid = customer_id_info['external_userid']
                    follow_userid = customer_id_info['follow_userid']

                    server_value = client.external_contact.get(external_userid)['external_contact']
                    server_value['unassigned_flag'] = False

                    ## 检查并更新本地客户信息
                    _logger.debug("server values: %s", server_value)
                    # if someone on server and in local
                    if external_userid in local_values:
                        temp_server_value = {
                            'name':  server_value.get('name'),
                            'avatar': server_value.get('avatar'),
                            'type': str(server_value.get('type')),
                            'gender': str(server_value.get('gender')),
                            'corp_name': server_value.get('corp_name'),
                            'corp_full_name': server_value.get('corp_full_name'),
                            'unassigned_flag': server_value.get('unassigned_flag'),
                            # 'follow_user': [v['userid'] for v in server_value.get('follow_user')] if server_value.get('follow_user') else [customer_id_info['follow_user_id']]
                            'follow_userid' : follow_userid
                        }
                        local_value = local_values[external_userid]
                        temp_local_value = {
                            'name': local_value['name'],
                            'avatar': local_value['avatar'],
                            'type': local_value['type'],
                            'gender': local_value['gender'],
                            'corp_name': local_value['corp_name'],
                            'corp_full_name': local_value['corp_full_name'],
                            'unassigned_flag': local_value['unassigned_flag'],
                            # 'follow_user': [v['user_code'] for v in local_value['follow_user']],
                            'follow_userid' : local_value['follow_userid']
                        }
                        # if have difference
                        if set(temp_server_value.items()) - set(temp_local_value.items()):
                            # replace follow user
                            # temp_server_value['follow_user'] = self.get_wechat_users(account.id,temp_server_value['follow_user'] )
                            self.env['odoo.wechat.enterprise.customer'].browse(local_value['id']).write(temp_server_value)
                        
                        # un registry local value
                        del local_values[external_userid]

                    # if someone on server but not in local
                    else:
                        _logger.info(u'Add missing server customer:%s', external_userid)
                        self.env['odoo.wechat.enterprise.log'].log_info(u'同步服务器用户', u'添加本地不存在用户:%s' % external_userid)

                        # follow_userids = [v['userid'] for v in server_value.get('follow_user')] if server_value.get('follow_user') else [customer_id_info['follow_user_id']]

                        new_server_value = {
                            'account' : account.id,
                            'external_userid': external_userid,
                            'name':  server_value.get('name'),
                            'avatar': server_value.get('avatar'),
                            'type': str(server_value.get('type')),
                            'gender': str(server_value.get('gender')),
                            'corp_name': server_value.get('corp_name'),
                            'corp_full_name': server_value.get('corp_full_name'),
                            'unassigned_flag': server_value.get('unassigned_flag'),
                            # 'follow_user' : self.get_wechat_users(account.id, follow_userids)
                            'follow_userid': follow_userid
                        }

                        self.env['odoo.wechat.enterprise.customer'].create(new_server_value)

                # delete customer on local but not on server
                if local_values:
                    mismatch_ids = [v['id'] for v in local_values.values()]
                    self.browse(mismatch_ids).write({'delete_flag': True})

                self.env['odoo.wechat.enterprise.log'].log_info(u'同步服务器用户-%s', u'同步完成')
                _logger.info(u'Sync wechat server customer data-%s', u'End')

                self.env['alert_message.wizard'].show_alert_message("服务器客户数据同步成功")

            except WeChatClientException as e:
                _logger.error(u'Get error in sync from server.%s', e)
                self.env['odoo.wechat.enterprise.log'].log_info(u'同步服务器用户失败-%s', str(e))
                self.env['alert_message.wizard'].show_alert_message("服务器客户数据同步失败.{}", str(e))


    def get_wechat_users(self, account_id, wechat_user_ids):
        """
        获取Follow企业微信用户
        """
        users = self.env['odoo.wechat.enterprise.user'].search_read([('account', '=', account_id),('user_code', 'in', wechat_user_ids)])

        _logger.debug('get_wechat_users results: %s', users)
        return users

    @staticmethod
    def get_unassigned_customer_list(wechat_client):
        """
        获取离职成员的客户列表
        """
        unassigned_customers =[]
        page_id = 0
        is_last = False
        while(not is_last):
            result = wechat_client.external_contact.get_unassigned_list(page_id, 1000)
            unassigned_customers.extend(result['info'])
            is_last = result['is_last']
            page_id +=1
        
        return unassigned_customers
  
    @staticmethod
    def get_customer_id_list(wechat_client):
        """
        获取客户ID列表
        """
        # get follow users
        _logger.debug('Get follow user list from wechat...')
        result = wechat_client.external_contact.get_follow_user_list()

        _logger.debug('Follow users result: %s', result)

        all_customer_ids = []
        # fetch customers of follow users
        for user_id in result['follow_user']:
            # get external customer id list
            try:
                customer_result = wechat_client.external_contact.list(user_id)
                _logger.debug('Customer query result for users id - %s. %s', user_id, customer_result)
                for customer_id in customer_result['external_userid']:
                    all_customer_ids.append({'follow_userid': user_id, 'external_userid':customer_id})
            except:
                 _logger.warn('Failed to get customer contact for user: %s', user_id)
        
        return all_customer_ids

   