import base64
import logging

from odoo import tools, exceptions
from odoo import models, fields, api
from odoo.tools.translate import _
from wechatpy.enterprise import WeChatClient

_logger = logging.getLogger(__name__)

class WelcomeMessageTemplate(models.Model):
    _name = 'odoo.wechat.enterprise.welcome_message_template'
    _rec_name = 'name'

    account = fields.Many2one('odoo.wechat.enterprise.account', 'Account', required=True)
    # Message content
    template_id = fields.Char("Template Id", readonly=True)
    name = fields.Char("Name")
    text = fields.Text('Text')
    addition_content_type = fields.Selection([('link', 'Link'), ('image', 'Image'), ('miniprogram', 'Mini Program')], 'Message Type', default='text', required=True)
    title = fields.Char('Title')
    url = fields.Text('URL')
    pic_url = fields.Text('Picture URL')
    desc = fields.Text('Description')
    program_id = fields.Text('MiniProgram AppId')
    program_page = fields.Text('MiniProgram Page')
    media_id = fields.Char("Media Id", readonly=True)

    # File
    file = fields.Many2many('ir.attachment', 'wechat_welcome_message_template_attachment_rel', '_message_template_id', 'attachment_id', 'Image File')

    @api.model
    def create(self, vals):
      
        if (vals.file and self.file[0]):
            media_id = self.upload_media_file(self.file[0])
            vals['media_id'] = media_id
        
        #self.env.cr.execute('SAVEPOINT welcome_message_template_create')
        message_template = super(WelcomeMessageTemplate, self).create(vals)
        # if self.env['ir.config_parameter'].get_param('wechat.sync') == 'True':
        #     try:
        #         message_template.create_wechat()
        #     except Exception as e:
        #         self.env.cr.execute('ROLLBACK TO SAVEPOINT welcome_message_template_create')
        #         raise exceptions.Warning(str(e))
        # self.env.cr.execute('RELEASE SAVEPOINT welcome_message_template_create')
        # return message_template

   
    def write(self, vals):

        if (vals.file and self.file[0]):
            media_id = self.upload_media_file(self.file[0])
            vals['media_id'] = media_id

        # self.env.cr.execute('SAVEPOINT welcome_message_template_write')
        result = super(WelcomeMessageTemplate, self).write(vals)
        # if self.env['ir.config_parameter'].get_param('wechat.sync') == 'True':
        #     try:
        #         self.write_wechat(vals)
        #     except Exception as e:
        #         self.env.cr.execute('ROLLBACK TO SAVEPOINT welcome_message_template_write')
        #         raise exceptions.Warning(str(e))
        # self.env.cr.execute('RELEASE SAVEPOINT welcome_message_template_write')
        return result

    def create_wechat(self):
        wechat_client = WeChatClient(self.account.corpid, self.account.app_secret)
        wechat_client.department.create(name=self.name, parent_id=self.parent_id.id or 1, order=self.order, id=self.id)
        for user in self.users:
            wechat_client.user.update(user.user_code, department=[d.id for d in user.departments] or [1])

   
    def write_wechat(self, vals):
        for record in self:
            wechat_client = WeChatClient(record.account.corpid, record.account.app_secret)
            content = self.create_template_content(record, wechat_client)

    def create_template_content(self, vals, wechat_client):
        content = {}
        if ( vals.text !=None ):
            content['text'] = {
                'content': vals['text']
            }
        
        if self.addition_content_type == 'link':
            content['link'] = {
                "title": vals['text'],
                "picurl": vals['pic_url'],
                "desc": vals['desc'],
                "url": vals['url']
            }
        elif vals.addition_content_type == 'image':
            content['image'] = {
                "media_id": vals['media_id'],
                "pic_url": vals['pic_url']
            }
        elif vals.addition_content_type == 'miniprogram':

            content['miniprogram'] = {
                    "title": vals['title'],
                    "pic_media_id": vals['media_id'],
                    "appid": vals['program_id'],
                    "page": vals['program_page']
                }
        
        return content

    def upload_media_file(self, file, wechat_client):
        media_file = ('message.jpg', base64.b64decode(file.datas))
        result = wechat_client.media.upload(media_type='image', media_file=media_file)
        media_id = result.get('media_id')
        return media_id

    @staticmethod
    def sent_welcome_message(self, corpid, external_userid):
        ''' Send welcome message to customer
        '''
        
        _logger.debug('Send welcome message start')

        # 1. get welcome message template
        account = self.env['odoo.wechat.enterprise.account'].search([('corpid', '=', corpid)])

        welcome_message_template = self.env['odoo.wechat.enterprise.customer_welcome_message'].search([('account', '=', account)])
        
        customer = self.env['odoo.wechat.enterprise.customer'].search([('external_userid', '=', external_userid)])
        # 2. create welcome message
        message_vals = {
           'account': account.id,
           'type': welcome_message_template.type,
           'title': welcome_message_template.title,
           'content': welcome_message_template.content,
           'url': welcome_message_template.url,
           'pic_url': welcome_message_template.pic_url,
           'program_id': welcome_message_template.program_id,
           'program_page': welcome_message_template.program_page,
           'customers': [customer.id]
        }
        message_model = self.env['odoo.wechat.enterprise.customer_message'].create(message_vals)

        # 3. send out the message
        message_model.sent_message()