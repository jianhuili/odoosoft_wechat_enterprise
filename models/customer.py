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
    _rec_name = 'name'

    external_userid = fields.Char('External User ID', readonly=True)
    name = fields.Char('Name', readonly=True)
    avatar = fields.Char('Avatar', readonly=True)
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

    follow_userid = fields.Char('Follow UserID', readonly=True)
    follow_user = fields.Many2one('odoo.wechat.enterprise.user', 'Follow User', readonly=True)
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

    def sync_wechat_server(self):
        """
        sync wechat server user info to local database
        """

        _logger.info(u'Sync wechat server customer data-%s', u'Start')
        accounts = self.env['odoo.wechat.enterprise.account'].search([])
        for account in accounts:
            try:
                wechat_client =  WeChatClient(account.corpid, account.app_secret)
                
                # get local customers
                local_values = {v['external_userid']: v for v in self.search_read([('account', '=', account.id)],
                                                                        ['external_userid','name', 'avatar', 'type', 'gender','corp_name', 'corp_full_name', 'follow_userid','follow_user', 'unassigned_flag'])}
 
                # fetch all customers
                customer_id_infos = self.get_customer_id_list(wechat_client)
   
                for customer_id_info in customer_id_infos:
                    external_userid = customer_id_info['external_userid']
                    follow_userid = customer_id_info['follow_userid']

                    server_value = wechat_client.external_contact.get(external_userid)['external_contact']
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
                            'follow_userid' : local_value['follow_userid']
                        }
                        # if have difference
                        if set(temp_server_value.items()) - set(temp_local_value.items()):
                            # replace follow user
                            follow_user = self.get_wechat_user(account.id, temp_server_value['follow_userid'])
                            temp_server_value['follow_user'] = follow_user['id'] if follow_user else None
                            self.env['odoo.wechat.enterprise.customer'].browse(local_value['id']).write(temp_server_value)
                        
                        # un registry local value
                        del local_values[external_userid]

                    # if someone on server but not in local
                    else:
                        _logger.info(u'Add missing server customer:%s', external_userid)
                        self.env['odoo.wechat.enterprise.log'].log_info(u'同步服务器用户', u'添加本地不存在用户:%s' % external_userid)

                        # follow_userids = [v['userid'] for v in server_value.get('follow_user')] if server_value.get('follow_user') else [customer_id_info['follow_user_id']]
                        follow_user = self.get_wechat_user(account.id, follow_userid)
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
                            'follow_user' :  follow_user['id'] if follow_user else None,
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

    def get_account(self, account_id):
        """
        获取客户Model
        """
        accounts = self.env['odoo.wechat.enterprise.account'].browse(account_id).read()

        _logger.debug('get_account results: %s', accounts)
        return accounts[0] if len(accounts) >=0 else None

    def get_customer(self, customer_id):
        """
        获取客户Model
        """
        customers = self.env['odoo.wechat.enterprise.customer'].browse(customer_id)

        _logger.debug('get_customer results: %s', customers)
        return customers[0] if len(customers) >=0 else None

    def get_wechat_user(self, account_id, wechat_user_id):
        """
        获取Follow企业微信用户
        """
        users = self.env['odoo.wechat.enterprise.user'].search([('account', '=', account_id),('wechat_id', '=', wechat_user_id)])

        _logger.debug('get_wechat_user results: %s', users)
        return users[0] if len(users) >=0 else None

    def get_wechat_user_by_id(self, user_id):
        """
        获取Follow企业微信用户
        """
        users = self.env['odoo.wechat.enterprise.user'].browse(user_id)

        _logger.debug('get_wechat_user results: %s', users)
        return users[0] if len(users) >=0 else None

    def button_transfer(self):
        """
        显示客户转移画面
        """
        _logger.debug('Enter button_transfer...')
        return {
            'name': "Transfer Customer",
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'odoo.wechat.enterprise.customer.transfer.wizard',
            'target': 'new'
        }

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

class CustomerTransferWizard(models.TransientModel):
    _name = 'odoo.wechat.enterprise.customer.transfer.wizard'
    _rec_name = 'account'
    _description = 'Customer Transfer Wizard'

    account = fields.Many2one('odoo.wechat.enterprise.account', 'Account', readonly=True)
    customer = fields.Many2one('odoo.wechat.enterprise.customer', 'Customer', readonly=True)
    current_follow_user = fields.Many2one('odoo.wechat.enterprise.user', 'Current Follow User', readonly=True)
    new_follow_user = fields.Many2one('odoo.wechat.enterprise.user', 'New Follow User')

    @api.model
    def default_get(self, fields_list):
        _logger.debug('Enter default_get')
        active_ids = self.env.context.get("active_ids")
        customer =  self.env["odoo.wechat.enterprise.customer"].browse(active_ids)
        _logger.debug('Customer results: %s', customer)
        defaults = {}
        if customer:
            defaults = {
                'account' : customer.account.id,
                'customer' : customer.id,
                'current_follow_user' : customer.follow_user.id,
            }
        return defaults

    def button_transfer(self):
        """
        客户再分配
        """
        _logger.debug('Enter button_transfer')
        for record in self:
            customer = record.customer
            current_follow_user = record.current_follow_user
            new_follow_user = record.new_follow_user
            
            self.transfer_customer(record, customer, current_follow_user, new_follow_user)
            
        ## close current window when succeed
        return {'type': 'ir.actions.act_window_close'}         
        # return {
        #     'type': 'ir.actions.act_window.message',
        #     'title': _('Customer Transfer'),
        #     'message': _('Customer transferred successfully'),
        # }

    def transfer_customer(self, record, customer, current_follow_user, new_follow_user):
        """
        客户再分配

        :param current_follow_user: 当前成员
        :param new_follow_user: 接替成员
        """
        _logger.debug('Enter button_transfer')
        # 1. get customer external id
        # customer = self.get_customer(customer_id)
        # if (customer == None):
        #     _logger.warning(u'Could not find customer data. Customer Id: %s', customer_id)
        #     raise exceptions.Warning('Could not find customer data. Customer Id: %s', customer_id)
        customer_user_id = customer.external_userid
        account = customer.account

        # # 1. check and get current follow user info
        # from_follow_user = self.get_wechat_user_by_id(from_follow_user_id)
        # if (from_follow_user == None):
        #     _logger.warning(u'Could not find current follow user data. Wechat User Id: %s', from_follow_user_id)
        #     raise exceptions.Warning('Could not find current follow user data. Wechat User Id: %s', from_follow_user_id)
        handover_userid = current_follow_user.wechat_id

        # # 2. check and get new follow user info

        # to_follow_user = self.get_wechat_user_by_id(to_follow_user_id)
        # if (to_follow_user == None):
        #     _logger.warning(u'Could not find new follow user data. Wechat User Id: %s', to_follow_user_id)
        #     raise exceptions.Warning('Could not find new follow user data. Wechat User Id: %s', to_follow_user_id)
        takeover_userid = new_follow_user.wechat_id

        # 3. do transfer
        wechat_client = WeChatClient(account.corpid, account.app_secret)
        _logger.debug(u'Transferring Customer.Customer external user id: %s, Current follow user id :%s, new follow user id: %s', customer_user_id, handover_userid, takeover_userid)
        process_result = wechat_client.external_contact.transfer(customer_user_id, handover_userid,takeover_userid)

        if (process_result['errcode'] == 0):
            ## update record
            ## the follow user info will not change immediately
            # customer_model = self.env['odoo.wechat.enterprise.customer'].browse(customer.id)
            # customer_model.write({'follow_user': new_follow_user,'follow_userid': new_follow_user.wechat_id})
            _logger.info(u'Customer transferred succeed.Customer external user id: %s, Current follow user id :%s, new follow user id: %s', customer_user_id, handover_userid, takeover_userid)
        else:
            # record.result = process_result['errmessage']
            _logger.warning(u'Customer transferred failed.Customer external user id: %s, Current follow user id :%s, new follow user id: %s', customer_user_id, handover_userid, takeover_userid)
            raise exceptions.Warning(_('Failed to transfer customer: %s'), customer_user_id)


