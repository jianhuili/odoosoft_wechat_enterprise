# coding=utf-8

import logging
from operator import itemgetter
from odoo import tools, exceptions
from odoo import models, fields, api
from odoo.tools.translate import _
from wechatpy.enterprise import WeChatClient

_logger = logging.getLogger(__name__)

class WechatDepartment(models.Model):
    _name = 'odoo.wechat.enterprise.department'
    _rec_name = 'name'
    _description = 'Wechat Enterprise Department'
    _order = 'parent_id desc, order'

    account = fields.Many2one('odoo.wechat.enterprise.account', 'Account', required=True)
    name = fields.Char('name', required=True)
    order = fields.Integer('Order', required=True)
    parent_id = fields.Many2one('odoo.wechat.enterprise.department', 'Parent')
    children_ids = fields.One2many('odoo.wechat.enterprise.department', 'parent_id', 'Children')
    users = fields.Many2many('odoo.wechat.enterprise.user', 'wechat_enterprise_department_user_rel', 'department_id', 'user_code', 'Users')

    _sql_constraints = [
        ('odoo_wechat_enterprise_department_name_unique', 'unique(name, parent_id, account)', _('name must be unique each parent!'))]

    @api.constrains('parent_id')
    def check_cycle(self):
        level = 100
        ids = self.ids
        while len(ids):
            self.env.cr.execute("""\
            SELECT DISTINCT parent_id
            FROM odoo_wechat_enterprise_department
            WHERE id IN %s AND parent_id IS NOT NULL""", [tuple(ids), ])
            ids = list(map(itemgetter(0), self.env.cr.fetchall()))
            if not level:
                raise exceptions.Warning(_('Error! You cannot create recursive Type.'))
            level -= 1

  
    def create_wechat(self):
        if self.env['ir.config_parameter'].get_param('wechat.sync') == 'True':
            client = WeChatClient(self.account.corpid, self.account.secret)
            client.department.create(name=self.name, parent_id=self.parent_id.id or 1, order=self.order, id=self.id)
            for user in self.users:
                client.user.update(user.user_code, department=[d.id for d in user.departments] or [1])

   
    def write_wechat(self, vals, department_old_user):
        if self.env['ir.config_parameter'].get_param('wechat.sync') == 'True':
            for department in self:
                client = WeChatClient(department.account.corpid, department.account.secret)
                client.department.update(department.id, name=department.name, parent_id=department.parent_id.id or 1, order=department.order)
                if 'users' in vals:
                    old_user = department_old_user[department]
                    new_user = [u.id for u in department.users]
                    need_update_users = self.env['odoo.wechat.enterprise.user'].browse(list(set(new_user) ^ set(old_user)))
                    for user in need_update_users:
                        client.user.update(user.user_code, department=[d.id for d in user.departments] or [1])


    @api.model
    def unlink_wechat(self):
        if self.env['ir.config_parameter'].get_param('wechat.sync') == 'True':
            for department in self:
                client = WeChatClient(department.account.corpid, department.account.secret)
                for user in department.users:
                    client.user.update(user.user_code, department=[d.id for d in user.departments if d.id != department.id] or [1])
                client.department.delete(department.id)

    @api.model
    def create(self, vals):
        self.env.cr.execute('SAVEPOINT wechat_department_create')
        department = super(WechatDepartment, self).create(vals)
        if 'is_no_wechat_sync' not in self.env.context:
            try:
                department.create_wechat()
            except Exception as e:
                self.env.cr.execute('ROLLBACK TO SAVEPOINT wechat_department_create')
                raise exceptions.Warning(str(e))
        self.env.cr.execute('RELEASE SAVEPOINT wechat_department_create')
        return department

   
    def write(self, vals):
        # self.check_account_unique()
        self.env.cr.execute('SAVEPOINT wechat_department_write')
        old_user = {}
        for department in self:
            old_user[department] = [u.id for u in department.users]
        result = super(WechatDepartment, self).write(vals)
        if 'is_no_wechat_sync' not in self.env.context:
            try:
                self.write_wechat(vals, old_user)
            except Exception as e:
                self.env.cr.execute('ROLLBACK TO SAVEPOINT wechat_department_write')
                raise exceptions.Warning(str(e))
        self.env.cr.execute('RELEASE SAVEPOINT wechat_department_write')
        return result

   
    def unlink(self):
        for department in self:
            if department.children_ids:
                raise exceptions.Warning(_("You can't delete department which have sub department."))
        self.env.cr.execute('SAVEPOINT wechat_department_unlink')
        if 'is_no_wechat_sync' not in self.env.context and self.ids:
            try:
                self.unlink_wechat()
            except Exception as e:
                self.env.cr.execute('ROLLBACK TO SAVEPOINT wechat_department_unlink')
                raise exceptions.Warning(str(e))
        result = super(WechatDepartment, self).unlink()
        self.env.cr.execute('RELEASE SAVEPOINT wechat_department_unlink')
        return result