
# coding=utf-8
from odoo import tools, exceptions
from odoo import models, fields, api
from odoo.tools.translate import _

class ResUserInherit(models.Model):
    _inherit = 'res.users'

    wechat_user = fields.One2many('odoo.wechat.enterprise.user', 'res_user', 'Wechat User')
    wechat_id = fields.Char('Wechat ID')

    def __init__(self, pool, cr):
        """ Override of __init__ to add access rights on
        display_employees_suggestions fields. Access rights are disabled by
        default, but allowed on some specific fields defined in
        self.SELF_{READ/WRITE}ABLE_FIELDS.
        """
        init_res = super(ResUserInherit, self).__init__(pool, cr)
        # duplicate list to avoid modifying the original reference
        self.SELF_WRITEABLE_FIELDS = list(self.SELF_WRITEABLE_FIELDS)
        self.SELF_WRITEABLE_FIELDS.extend(['wechat_id', 'wechat_user'])
        # duplicate list to avoid modifying the original reference
        self.SELF_READABLE_FIELDS = list(self.SELF_READABLE_FIELDS)
        self.SELF_READABLE_FIELDS.extend(['wechat_id', 'wechat_user'])
        return init_res

   
    def unlink(self):
        for user in self:
            user.wechat_user.sudo().unlink()
        res = super(ResUserInherit, self).unlink()
        return res

   
    def write(self, vals):
        self.env.cr.execute('SAVEPOINT user_write')
        result = super(ResUserInherit, self).write(vals)
        if ('mobile' in vals or 'wechat_id' in vals or 'email' in vals) and 'is_no_wechat_sync' not in self.env.context:
            try:
                for user in self:
                    user.wechat_user.sudo().write({
                        'res_user': user.id,
                        'wechat_id': user.wechat_id,
                        'email': user.email,
                        'mobile': user.mobile,
                    })
            except Exception as e:
                self.env.cr.execute('ROLLBACK TO SAVEPOINT user_write')
                raise exceptions.Warning(str(e))
        self.env.cr.execute('RELEASE SAVEPOINT user_write')
        return result

