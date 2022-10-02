# coding=utf-8

from wechatpy.enterprise.exceptions import InvalidCorpIdException
from wechatpy.enterprise import WeChatClient, WeChatCrypto, parse_message, create_reply
from wechatpy.exceptions import InvalidSignatureException
from werkzeug.exceptions import abort
import logging
from odoo import http

_logger = logging.getLogger(__name__)


class WechatControllers(http.Controller):
    @http.route('/wechat_enterprise/<string:code>/api', type='http', auth="public", methods=['GET', 'POST'])
    def process(self, request, code, msg_signature, timestamp, nonce, echostr=None):
        _logger.debug('WeChat Enterprise connected:  code=%s, msg_signature=%s, timestamp=%s, nonce=%s, echostr=%s', code, msg_signature, timestamp,
                      nonce, echostr)
        request.uid = 1
        account_obj = request.registry['odoo.wechat.enterprise.account']
        account = account_obj.search(request.cr, request.uid, [('code', '=', code)], context=request.context)
        if not account:
            _logger.warning('Cant not find webchat account.')
            abort(403)
        else:
            account = account_obj.browse(request.cr, request.uid, account[0], context=request.context)
        wechat_crypto = WeChatCrypto(account.token, account.ase_key, account.corpid)

        if request.httprequest.method == 'GET':
            echo_str = ''
            try:
                echo_str = wechat_crypto.check_signature(
                    msg_signature,
                    timestamp,
                    nonce,
                    echostr
                )
            except InvalidSignatureException:
                _logger.warning('check_signature fail.')
                abort(403)
            return echo_str
        else:
            try:
                msg = wechat_crypto.decrypt_message(
                    request.httprequest.data,
                    msg_signature,
                    timestamp,
                    nonce
                )
                msg = parse_message(msg)
                reply_msg = account.process_request(msg)
                if reply_msg:
                    # if isinstance(reply_msg, list):
                    # reply_msg = reply_msg[0]
                    return wechat_crypto.encrypt_message(reply_msg.render(), nonce, timestamp)
                else:
                    _logger.info('reply None! msg= %s', msg)
                    return ''
            except (InvalidSignatureException, InvalidCorpIdException) as e:
                _logger.warning('decrypt_message fail. %s', e)
                request.registry['odoo.wechat.enterprise.log'].log_info(request.cr, 1, u'过滤器', 'decrypt_message fail. %s' % e,
                                                                            context=request.context)
                return ''
            except Exception as e:
                _logger.error('process_request error: %s', e)
                request.registry['odoo.wechat.enterprise.log'].log_info(request.cr, 1, u'过滤器', 'process_request error: %s' % e,
                                                                            context=request.context)
                return ''

    @http.route('/wechat_enterprise/<string:code>/api/debug', type='http', auth="public", methods=['GET', 'POST'])
    def process_debug(self, request, code, msg_signature, timestamp, nonce, msg=None, echostr=None):
        _logger.debug('WeChat Enterprise connected:  code=%s, msg_signature=%s, timestamp=%s, nonce=%s, echostr=%s', code, msg_signature, timestamp,
                      nonce, echostr)
        request.uid = 1
        account_obj = request.registry['odoo.wechat.enterprise.account']
        account = account_obj.search(request.cr, request.uid, [('code', '=', code)], context=request.context)
        if not account:
            _logger.warning('Cant not find account.')
            abort(403)
        else:
            account = account_obj.browse(request.cr, request.uid, account[0], context=request.context)
        # wechat_crypto = WeChatCrypto(account.token, account.ase_key, account.corpid)

        try:
            reply_msg = account.process_request(msg)
            if reply_msg:
                # if isinstance(reply_msg, list):
                # reply_msg = reply_msg[0]
                reply = create_reply(reply_msg, msg).render()
                _logger.info('reply_msg is %s', reply)
                request.registry['odoo.wechat.enterprise.log'].log_info(request.cr, 1, u'过滤器', reply,
                                                                            context=request.context)
                return ''
            else:
                request.registry['odoo.wechat.enterprise.log'].log_info(request.cr, 1, u'过滤器', 'reply_msg is None',
                                                                            context=request.context)
                _logger.info('reply_msg is None')
        except Exception as e:
            _logger.error('process_request error: %s', e)
            request.registry['odoo.wechat.enterprise.log'].log_info(request.cr, 1, u'过滤器', 'process_request error: %s' % e,
                                                                        context=request.context)
            return ''