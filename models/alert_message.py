
from odoo import models, fields, api, exceptions

class AlertMessageWizard(models.TransientModel):
    _name = 'alert_message.wizard'

    message = fields.Text('Message', required=True)

    def action_ok(self):
        """ close wizard"""
        return {'type': 'ir.actions.act_window_close'}

    def show_alert_message(self, message, *args):
        # don't forget to add translation support to your message _()
        message_id = self.create({'message': message.format(args)})
        return {
            'name': 'AlertMessage',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'alert_message.wizard',
            # pass the id
            'res_id': message_id.id,
            'target': 'new'
    }

    