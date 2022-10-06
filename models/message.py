# coding=utf-8
import base64
from io import StringIO
import logging

from urllib import parse
from odoo import tools
from odoo import models, fields, api
from odoo.tools.translate import _
from wechatpy.enterprise import WeChatClient

_logger = logging.getLogger(__name__)

class Message(models.Model):
    _name = 'odoo.wechat.enterprise.message'
    _order = 'id desc'
    _rec_name = 'status'

    status = fields.Selection([('draft', 'Draft'), ('send', 'Send'), ('fail', 'Fail')], 'Status', default='draft')
    type = fields.Selection([('text', 'Text'), ('news', 'News'), ('image', 'Image')], 'Message Type', default='text', required=True)

    account = fields.Many2one('odoo.wechat.enterprise.account', 'Account', required=True)
    users = fields.Many2many('odoo.wechat.enterprise.user', 'rel_wechat_ep_message_user', 'message_id', 'user_code', 'Users')
    departments = fields.Many2many('odoo.wechat.enterprise.department', 'rel_wechat_ep_message_department', 'message_id', 'department_id',
                                   'Departments')
    res_users = fields.Many2many('res.users', 'rel_wechat_ep_res_user', 'message_id', 'user_id', 'Odoo Users')
    create_user = fields.Many2one('res.users', 'Create User')

    # res_model = fields.Char('Res Model Name')
    # res_id = fields.Integer('Res Id')
    # res_name = fields.Char('Res Name')

    # News Template
    title = fields.Char('Title')
    content = fields.Text('Content')
    template = fields.Many2one('odoo.wechat.enterprise.message.template', 'Message Template')

    # File
    file = fields.Many2many('ir.attachment', 'wechat_message_attachment_rel', 'message_id', 'attachment_id', 'Image File')

    result = fields.Text('result')
    send_time = fields.Datetime('Send Time')

    @api.model
    def process_message(self):
        self.search([('status', '=', 'draft')]).sent_message()

   
    def sent_message(self):
        for message in self:
            target_users = message.users
            if message.res_users:
                target_users = self.env['odoo.wechat.enterprise.user'].search(
                    ['|', '&',
                     ('res_user', 'in', [u.id for u in message.res_users]),
                     ('account', '=', message.account.id),
                     ('id', 'in', [u.id for u in target_users])])
            user_ids = '|'.join([u.user_code for u in target_users])
            message.users = target_users
            if target_users or message.departments:
                try:
                    client = WeChatClient(message.account.corpid, message.account.secret)
                    # TODO: all support
                    if message.type == 'text':
                        client.message.send_text(message.account.id, user_ids,
                                                 party_ids='|'.join([str(d.id) for d in message.departments]), content=message.text_message_content())
                    elif message.type == 'news':
                        client.message.send_articles(message.account.id, user_ids,
                                                     party_ids='|'.join([str(d.id) for d in message.departments]),
                                                     articles=message.news_message_content())
                    elif message.type == 'image':
                        if self.file:
                            media_file = ('test.jpg', base64.b64decode(self.file[0].datas))
                            result = client.media.upload(media_type='image', media_file=media_file)
                            client.message.send_image(message.account.id, user_ids,
                                                      media_id=result['media_id'],
                                                      party_ids='|'.join([str(d.id) for d in message.departments]),
                                                      )
                    message.status = 'send'
                    message.result = u'成功'
                    message.send_time = fields.Datetime.now()
                except Exception as e:
                    message.write({'status': 'fail', 'result': str(e), 'send_time': fields.Datetime.now()})
            else:
                message.write({'status': 'fail', 'result': u'没有可发送对象', 'send_time': fields.Datetime.now()})

   
    def get_url(self):
        if self.template.is_no_url:
            return ''
        oath_url = 'https://open.weixin.qq.com/connect/oauth2/authorize?appid=%(CORPID)s' + \
                   '&redirect_uri=%(REDIRECT_URI)s&response_type=code&scope=snsapi_base&state=%(STATE)s#wechat_redirect'
        have_mobile = self.sudo().env['ir.module.module'].search([('status', '=', 'installed'), ('name', '=', 'odoo_mobile')])
        if self.template.url:
            index = self.sudo().env['ir.config_parameter'].get_param('wechat.base.url') + self.template.url.format(**{
                # 'res_id': self.res_id,
                # 'res_model': self.res_model,
                # 'res_name': self.res_name,
                'account_code': self.account.code
            })
        else:
            if have_mobile:
                index = "%s/mobile?#action=mail.action_mail_redirect&model=%s&res_id=%s"
            else:
                index = "%s/web?#action=mail.action_mail_redirect&model=%s&res_id=%s"
            index = index % (
                self.sudo().env['ir.config_parameter'].get_param('wechat.base.url'), self.res_model, self.res_id)
        url = oath_url % {
            'CORPID': self.account.corpid,
            'REDIRECT_URI': parse.quote_plus(index),
            'STATE': self.account.code,
        }
        if have_mobile:
            return url
        else:
            return index

   
    def text_message_content(self):
        if self.res_model and self.res_id:
            html_code = "<a href='%s'>%s</a>"
            content = html_code % (self.get_url(), self.res_name) + '\n' + self.content
        else:
            content = self.content
        return content

   
    def news_message_content(self):
        article = {}
        # url
        if self.res_model and self.res_id:
            article['url'] = self.get_url()
        else:
            article['url'] = ''
        # title
        article['title'] = self.title if self.title else (self.template.title if self.template else '')
        # description
        if self.template:
            article['description'] = self.template.render(self.env[self.res_model].browse(self.res_id)) + '\n' + self.content
        else:
            article['description'] = self.content
        # image
        article['image'] = None

        return [article]

    @api.model
    def create_message(self, obj, content, code, user_ids=None, type='text', template=None, title=None, group_ids=None):
        sudo_user = self.sudo()
        group_users = []
        if not user_ids:
            user_ids = []
        if isinstance(code, int):
            account = sudo_user.env['odoo.wechat.enterprise.map'].browse(code).account
        else:
            account = sudo_user.env['odoo.wechat.enterprise.map'].get_map(code)
        if group_ids:
            for g_id in group_ids.split(','):
                group_users += [u.id for u in self.env.ref(g_id).users]
        if template and isinstance(template, str):
            result = self.env['odoo.wechat.enterprise.message.template'].search([('code', '=', template)])
            template = result.id if result else False
            if not template:
                template = self.env.ref(template).id

        if (user_ids or group_users) and account:
            sudo_user.create({
                'account': account.id,
                'res_users': [(6, 0, list(set(user_ids + group_users)))],
                'content': content,
                'create_user': self.env.uid,
                # 'res_model': obj._name if obj else False,
                # 'res_id': obj.id if obj else False,
                # 'res_name': obj.name_get()[0][1] if obj else False,
                'type': type,
                'template': template,
                'title': title,
            })
