# coding=utf-8
import base64
from io import StringIO
import logging

from urllib import parse
from odoo import tools, exceptions
from odoo import models, fields, api
from odoo.tools.translate import _
from wechatpy.enterprise import WeChatClient

_logger = logging.getLogger(__name__)

class CustomerMessage(models.Model):
    _name = 'odoo.wechat.enterprise.customer_message'
    _order = 'id desc'
    _rec_name = 'state'

    state = fields.Selection([('draft', 'Draft'), ('send', 'Send'), ('fail', 'Fail')], 'State', default='draft')
    type = fields.Selection([('text', 'Text'), ('link', 'Link'), ('image', 'Image'), ('miniprogram', 'Mini Program')], 'Message Type', default='text', required=True)

    account = fields.Many2one('odoo.wechat.enterprise.account', 'Account', required=True)
    customers = fields.Many2many('odoo.wechat.enterprise.customer', 'rel_wechat_ep_customer_message_customer', 'message_id', 'wechatcustomer_id', 'Customers')

    create_user = fields.Many2one('res.users', 'Create User')

    # res_model = fields.Char('Res Model Name')
    # res_id = fields.Integer('Res Id')
    # res_name = fields.Char('Res Name')

    # Message content
    title = fields.Char('Title')
    content = fields.Text('Content')
    url = fields.Text('URL')
    pic_url = fields.Text('Picture URL')
    program_id = fields.Text('MiniProgram AppId')
    program_page = fields.Text('MiniProgram Page')

    template = fields.Many2one('odoo.wechat.enterprise.message.template', 'Message Template')

    # File
    file = fields.Many2many('ir.attachment', 'wechat_customer_message_attachment_rel', 'message_id', 'attachment_id', 'Image File')

    result = fields.Text('result')
    send_time = fields.Datetime('Send Time')

    @api.model
    def process_message(self):
        self.search([('state', '=', 'draft')]).sent_message()

    def sent_message(self):
        for message in self:
            client = WeChatClient(message.account.corpid, message.account.app_secret)
            target_customers = message.customers
            if target_customers:
                try:
                    # send seperate message for each customer
                    for target_customer in target_customers:
                        message_template = {
                            "external_userid": target_customer['external_userid'],
                            # "sender": 
                        }                 
                        if message.type == 'text':
                            message_template['text'] = {"content": message.text_message_content()}
                        elif message.type == 'link':
                            message_template['attachments'] = [ {"msgtype": "link", "link": message.link_message_content()}]
                        elif message.type == 'image':
                            media_file = ('message.jpg', base64.b64decode(self.file[0].datas))
                            result = client.media.upload(media_type='image', media_file=media_file)
                            message_template['attachments'] = [{"msgtype": "image", "image": {"media_id":result.get('media_id')}}]
                        elif message.type == 'miniprogram':
                            if (self.file and self.file[0]):
                                media_file = ('message.jpg', base64.b64decode(self.file[0].datas))
                                result = client.media.upload(media_type='image', media_file=media_file)
                                content_data = self.mini_program_content( target_customer['external_userid'], result.get('media_id'))
                            else:
                                content_data = self.mini_program_content(target_customer['external_userid'])
                            message_template['attachments'] = [{"msgtype": "miniprogram", "miniprogram": content_data}]

                        # sending message
                        send_result = client.external_contact.add_msg_template(message_template)
                        if (send_result['errcode'] !=0 ):
                            _logger.warning("Failed to send customer message to customer. external_user_id=%s. error detail:", target_customer.external_userid, send_result['errmsg'])
                    
                    message.state = 'send'
                    message.result = u'成功'
                    message.send_time = fields.Datetime.now()
                except Exception as e:
                    message.write({'state': 'fail', 'result': str(e), 'send_time': fields.Datetime.now()})
            else:
                message.write({'state': 'fail', 'result': u'没有可发送对象', 'send_time': fields.Datetime.now()})
   
    def text_message_content(self):
        content = self.content
        return content
 
    def link_message_content(self):
        content_data = {}
        # url
        content_data['url'] = self.url
        # title
        content_data['title'] = self.title if self.title else (self.template.title if self.template else '')
        # description
        content_data['desc'] = self.content
        # image url
        content_data['picurl'] = self.pic_url

        return content_data

    def mini_program_content(self, external_user_id, media_id=None):
        content_data = {}

        # title
        content_data['title'] = self.title if self.title else (self.template.title if self.template else '')
        # pic_media_id
        content_data['pic_media_id'] = media_id
        # app id
        content_data['appid'] = self.program_id
        # page
        if ('?' in self.program_page ):
            content_data['page'] = '%s&external_userid=%s'.format(self.program_page,external_user_id)
        else:
            content_data['page'] = '%s?external_userid=%s'.format(self.program_page,external_user_id)

        return content_data

