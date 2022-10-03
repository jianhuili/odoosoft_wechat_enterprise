# coding=utf-8

import time
from odoo import tools
import logging
from odoo import models, fields, api, exceptions
from odoo.tools.translate import _
from wechatpy.enterprise import WeChatClient
from wechatpy.exceptions import WeChatClientException

_logger = logging.getLogger(__name__)


class WechatUser(models.Model):
    _name = 'odoo.wechat.enterprise.user'
    #_rec_name = 'login'

    state = fields.Selection([('1', 'Stared'), ('4', 'Not Stared'), ('2', 'Frozen'), ('10', 'Server No Match')], 'State', default='4')

    user_code = fields.Char('User ID', required=True)
    name = fields.Char('Name', required=True)

    user = fields.Many2one('res.users', 'User')
    mobile = fields.Char('Mobile')
    email = fields.Char('Email')
    wechat_id = fields.Char('Wechat ID')


    job = fields.Char('Job')
    departments = fields.Many2many('odoo.wechat.enterprise.department', 'wechat_enterprise_department_user_rel', 'user_code', 'department_id',
                                   'Departments')

    account = fields.Many2one('odoo.wechat.enterprise.account', 'Account', required=True)

    active = fields.Boolean('Active', default=True)

    @api.onchange('user')
    def onchange_user(self):
        self.user_code = self.user.login if self.user_code == None else self.user_code
        self.name = self.user.name
        self.mobile = self.user.mobile
        self.email = self.user.email
        self.wechat_id = self.user.wechat_id


    @api.constrains('wechat_id', 'mobile', 'email')
    def _check_wechat_info(self):
        if not self.wechat_id and not self.mobile and not self.email:
            raise exceptions.Warning(_('wechat_id, mobile, email can not be all none'))

  
    def create_wechat_account(self):
        if self.env['ir.config_parameter'].get_param('wechat.sync') == 'True':
            client = WeChatClient(self.account.corpid, self.account.secret)
            client.user.create(user_code=self.user_code, name=self.name, department=[d.id for d in self.departments] or [1], position=self.job,
                               mobile=self.mobile, email=self.email, wechat_id=self.wechat_id)

    @api.model
    def unlink_wechat_account(self, userids, account):
        if self.env['ir.config_parameter'].get_param('wechat.sync') == 'True':
            client = WeChatClient(account.corpid, account.secret)
            client.user.batch_delete(user_ids=userids)

    # @api.model_create_multi
    def write_wechat_account(self):
        if self.env['ir.config_parameter'].get_param('wechat.sync') == 'True':
            for record in self:
                client = WeChatClient(record.account.corpid, record.account.secret)
                # is user exist
                wechat_user_info = client.user.get(record.user_code)
                # if exist, update
                remote_val = {
                    'name': record.name if record.name else wechat_user_info.get('name'),
                    'position': record.job if record.job else wechat_user_info.get('position'),
                    'mobile': record.mobile if record.mobile else wechat_user_info.get('mobile'),
                    'email': record.email if record.email else wechat_user_info.get('email'),
                    'weixin_id': record.wechat_id if record.wechat_id else wechat_user_info.get('wechat_id'),
                    'department': [d.id for d in record.departments] or [1],
                }

                local_values = remote_val.copy()
                local_values['job'] = local_values['position']
                local_values['wechat_id'] = local_values['weixin_id']

                client.user.update(user_code=record.user_code, **remote_val)
                record.with_context(is_no_wechat_sync=True).write(local_values)

   
    def write(self, vals):
        # self.check_account_unique()
        self.env.cr.execute('SAVEPOINT wechat_write')
        result = super(WechatUser, self).write(vals)
        if 'is_no_wechat_sync' not in self.env.context:
            try:
                self.write_wechat_account()
            except Exception as e:
                self.env.cr.execute('ROLLBACK TO SAVEPOINT wechat_write')
                raise exceptions.Warning(str(e))
        self.env.cr.execute('RELEASE SAVEPOINT wechat_write')
        return result

    @api.model
    def create(self, vals):
        self.env.cr.execute('SAVEPOINT wechat_create')
        # if 'user_code' not in vals:
        #     vals['user_code'] = self.env['ir.sequence'].get('user_code')
        user = super(WechatUser, self).create(vals)
        if 'is_no_wechat_sync' not in self.env.context:
            try:
                user.create_wechat_account()
            except Exception as e:
                self.env.cr.execute('ROLLBACK TO SAVEPOINT wechat_create')
                raise exceptions.Warning(str(e))
        self.env.cr.execute('RELEASE SAVEPOINT wechat_create')
        return user

   
    def check_account_unique(self):
        if self.ids:
            self.env.cr.execute("""
                    SELECT count(id), account FROM odoo_wechat_enterprise_user
                    WHERE id in %s
                    GROUP BY account
                """, (tuple(self.ids),))
            res = self.env.cr.fetchall()
            if len(res) > 1:
                raise exceptions.Warning(_("Can't delete two account's user in one time."))

   
    def unlink(self):
        self.check_account_unique()
        self.env.cr.execute('SAVEPOINT wechat_unlink')
        userids = [u.user_code for u in self]
        if self.ids:
            account = self[0].account
        result = super(WechatUser, self).unlink()
        if 'is_no_wechat_sync' not in self.env.context and self.ids:
            try:
                self.unlink_wechat_account(userids, account)
            except Exception as e:
                self.env.cr.execute('ROLLBACK TO SAVEPOINT wechat_unlink')
                raise exceptions.Warning(str(e))
        self.env.cr.execute('RELEASE SAVEPOINT wechat_unlink')
        return result

   
    def unlink_force(self):
        self.with_context(is_no_wechat_sync=True).unlink()

   
    def create_force(self):
        try:
            self.create_wechat_account()
        except Exception as e:
            raise exceptions.Warning(str(e))

   
    def write_force(self):
        try:
            self.write_wechat_account()
        except Exception as e:
            raise exceptions.Warning(str(e))

   
    def button_invite(self):
        for record in self:
            try:
                record.account.get_client().user.invite(user_code=record.user_code)
            except WeChatClientException as e:
                if e.errcode == 60119:  # message: contact already joined
                    record.state = '1'
                else:
                    raise e

    @api.model
    def sync_wechat_server(self):
        """
        sync wechat server user info to local database
        """
        accounts = self.env['odoo.wechat.enterprise.account'].search([])
        for account in accounts:
            try:
                client = account.get_client()
                server_values = client.user.list(department_id=1, fetch_child=True)
                local_values = {v['user_code']: v for v in self.search_read([('account', '=', account.id)],
                                                                        ['state', 'user_code', 'name', 'mobile', 'email', 'wechat_id', 'job', ])}
                for server_value in server_values:
                    # if someone on server and in local
                    if server_value['user_code'] in local_values:
                        user_code = server_value['user_code']
                        temp_server_value = {
                            'wechat_id': server_value.get('wechat_id', False),
                            'name': server_value['name'],
                            'mobile': server_value.get('mobile', False),
                            'job': server_value.get('position', False),
                            'email': server_value.get('email', False),
                            'state': str(server_value['status']),
                        }
                        temp_local_value = {
                            'wechat_id': local_values[user_code]['wechat_login'],
                            'name': local_values[user_code]['name'],
                            'mobile': local_values[user_code].get('mobile', False) or False,
                            'job': local_values[user_code].get('job', False) or False,
                            'email': local_values[user_code].get('email', False) or False,
                            'state': local_values[user_code]['state'],
                        }
                        # if have difference
                        if set(temp_server_value.items()) - set(temp_local_value.items()):
                            self.env['odoo.wechat.enterprise.user'].browse(local_values[user_code]['id']).with_context(
                                is_no_wechat_sync=True).write(temp_server_value)
                        # un registry local value
                        del local_values[user_code]
                    # if someone on server but not in local
                    else:
                        _logger.warning('miss match server user:%s', server_value['user_code'])
                        self.env['odoo.wechat.enterprise.log'].log_info(u'同步服务器用户', u'服务器用户:%s没有在本机找到对应关系' % server_value['user_code'])
                # if someone on local but not on server
                if local_values:
                    mismatch_ids = [v['id'] for v in local_values.values()]
                    self.with_context(is_no_wechat_sync=True).browse(mismatch_ids).write({'state': '10'})
            except WeChatClientException as e:
                _logger.error('Get error in sync from server', e)
                self.env['odoo.wechat.enterprise.log'].log_info(u'同步服务器用户', str(e))
        self.env['odoo.wechat.enterprise.log'].log_info(u'同步服务器用户', u'同步完成')


class WechatWizard(models.TransientModel):
    _name = 'odoo.wechat.enterprise.user.wizard'

    user = fields.Many2one('res.users', 'User')
    account = fields.Many2one('odoo.wechat.enterprise.account', 'Account', required=True)
    wechat_id = fields.Char('Wechat Account')
    mobile = fields.Char('Mobile')
    email = fields.Char('Email')

  
    @api.constrains('wechat_id', 'mobile', 'email')
    def _check_wechat_info(self):
        if not self.wechat_id and not self.mobile and not self.email:
            raise exceptions.Warning(_('wechat_id, mobile, email can not be all none'))

    @api.model
    def default_get(self, fields_list):
        result = super(WechatWizard, self).default_get(fields_list)
        user = self.env['res.users'].search([('id', '=', self.env.context['active_id'])]).ensure_one()
        result['mobile'] = user.mobile
        result['email'] = user.email
        result['wechat_id'] = user.wechat_id
        result['user'] = user.id
        return result

   
    def create_wechat_user(self):
        if self.mobile:
            self.user.mobile = self.mobile
        if self.email:
            self.user.email = self.email
        if self.wechat_id:
            self.user.wechat_id = self.wechat_id
        value = {
            'user': self.user.id,
            'account': self.account.id,
            'name': self.user.name,
            'wechat_id': self.user.wechat_id,
            'email': self.user.email,
            'mobile': self.user.mobile,
        }
        self.env['odoo.wechat.enterprise.user'].create(value)
        self.env['res.users'].with_context(is_no_wechat_sync=True).write({
            'wechat_id': self.user.wechat_id,
            'email': self.user.email,
            'mobile': self.user.mobile,
        })
        return True


class UserCreateWizard(models.TransientModel):
    _name = 'odoo.wechat.enterprise.user.batch.wizard'
    _rec_name = 'account'

    account = fields.Many2one('odoo.wechat.enterprise.account', 'Account', required=True)
    res_users = fields.Many2many('res.users', 'wechat_batch_res_user_rel', 'batch_id', 'user_code', 'Need Process Users')
    processed_users = fields.Many2many('res.users', 'wechat_batch_res_processed_user_rel', 'batch_id', 'user_code', 'Processed Users')
    create_users = fields.Many2many('odoo.wechat.enterprise.user', 'wechat_batch_user_rel', 'batch_id', 'user_code', 'Create Users')
    result = fields.Char('Result')

   
    def button_batch_create(self):
        processed_users = []
        result = ''
        new_wechat_users = []
        for user in self.res_users:
            value = {
                'user': user.id,
                'account': self.account.id,
                'name': user.name,
                'wechat_id': user.wechat_id,
                'email': user.email,
                'mobile': user.mobile,
            }
            try:
                new_wechat_users += self.env['odoo.wechat.enterprise.user'].create(value)
                processed_users += user
            except Exception as e:
                result += '%s %s\n' % (user.name, str(e))

        value = {
            'res_users': [(3, u.id) for u in processed_users],
            'create_users': [(4, u.id) for u in new_wechat_users],
            'result': result or u'成功',
            'processed_users': [(4, u.id) for u in processed_users]
        }
        self.write(value)

        res = self.env['ir.actions.act_window'].for_xml_id('odoo_wechat_enterprise', 'action_wechat_batch_user')
        res['res_id'] = self[0].id
        return res

   
    def button_batch_create_fast(self):
        processed_users = []
        result = ''
        new_wechat_users = []
        # create inactive user
        self.env.cr.execute('SAVEPOINT wechat_update_extend')
        for user in self.res_users:
            value = {
                'user': user.id,
                'account': self.account.id,
                'name': user.name,
                'wechat_id': user.wechat_id,
                'email': user.email,
                'mobile': user.mobile,
                'active': False,
            }
            try:
                new_wechat_users += self.env['odoo.wechat.enterprise.user'].create(value)
                processed_users += user
            except Exception as e:
                result += '%s %s\n' % (user.name, str(e))
        if result:
            self.env.cr.execute('ROLLBACK TO SAVEPOINT wechat_update_extend')
            value = {
                'result': result,
            }
        else:
            self.env.cr.execute('RELEASE SAVEPOINT wechat_update_extend')
            # create csv file depends on new user information
            csv_file = u'姓名,帐号,微信号,手机号,邮箱,所在部门,职位\n'
            for user in new_wechat_users:
                csv_file += u'%s,%s,%s,%s,%s,%s,\n' % (user.name, user.user_code, user.wechat_id or '', user.mobile or '', user.email or '', 1)
            csv_file = ('temp.csv', csv_file)
            # upload csv file
            client = WeChatClient(self.account.corpid, self.account.secret)
            media = client.media.upload(media_type='file', media_file=csv_file)
            app = self.env.ref('odoo_wechat_enterprise.account_default')
            job_id = client.batch.sync_user(encoding_aes_key=app.ase_key, media_id=media['media_id'], token=app.token, url=app.token)['jobid']
            value = {
                'res_users': [(3, u.id) for u in processed_users],
                'create_users': [(4, u.id) for u in new_wechat_users],
                'result': u'成功,请退出向导,等待一段时间后查看用户是否成功创建',
                'processed_users': [(4, u.id) for u in processed_users]
            }
        self.write(value)

        res = self.env['ir.actions.act_window'].for_xml_id('odoo_wechat_enterprise', 'action_wechat_batch_user')
        res['res_id'] = self[0].id
        return res


class WechatInviteWizard(models.TransientModel):
    _name = 'odoo.wechat.enterprise.user.batch.invite.wizard'
    _rec_name = 'account_id'
    _description = 'Batch Invite Wizard'

    account_id = fields.Many2one('odoo.wechat.enterprise.account', 'Account')
    user_ids = fields.Many2many('odoo.wechat.enterprise.user', 'invite_wizard_user_rel', 'invite_id', 'user_code', 'Need Invite Users')

    @api.model
    def default_get(self, fields_list):
        result = super(WechatInviteWizard, self).default_get(fields_list)
        users = self.env['odoo.wechat.enterprise.user'].search([('id', '=', self.env.context['active_ids']), ('state', '=', '4')])
        result['user_ids'] = [(6, 0, [u.id for u in users])]
        account_id = list(set([u.account.id for u in users]))
        if len(account_id) == 1:
            result['account_id'] = account_id[0]
        else:
            raise exceptions.Warning(_('Choose multi accounts users in one sync or no user need to be invited!'))
        return result

   
    def button_batch_invite(self):
        app = self.env['odoo.wechat.enterprise.account'].search(
            [('account', '=', self.account_id.id)]).ensure_one()
        self.account_id.get_client().batch.invite_user(app.url, app.token, app.ase_key, [u.user_code for u in self.user_ids])
        return {
            'type': 'ir.actions.act_window.message',
            'title': _('Invite Send'),
            'message': _('Invite Already send'),
        }
