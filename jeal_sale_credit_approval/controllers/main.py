# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request


class CreditApprovalController(http.Controller):

    def _get_request(self, name, token):
        """Localiza la solicitud por número (con guiones) y token."""
        real_name = (name or '').replace('-', '/')
        req = request.env['sale.credit.approval.request'].sudo().search([
            ('name', '=', real_name),
            ('token', '=', token),
        ], limit=1)
        return req

    def _render(self, req, extra=None):
        values = {'req': req}
        if extra:
            values.update(extra)
        return request.render(
            'jeal_sale_credit_approval.credit_public_page', values)

    @http.route(['/credit/solicitud/<string:name>'], type='http',
                auth='public', website=False, csrf=False, methods=['GET'])
    def credit_page(self, name, token=None, action='approve', **kw):
        req = self._get_request(name, token)
        if not req:
            return request.render(
                'jeal_sale_credit_approval.credit_public_invalid', {})
        return self._render(req, {'action': action, 'done': False})

    @http.route(['/credit/solicitud/<string:name>/do'], type='http',
                auth='public', website=False, csrf=False, methods=['POST'])
    def credit_do(self, name, token=None, action='approve',
                  rejection_reason=None, **kw):
        req = self._get_request(name, token)
        if not req:
            return request.render(
                'jeal_sale_credit_approval.credit_public_invalid', {})
        if not req.sudo()._is_valid():
            return self._render(req, {'action': action, 'done': True,
                                      'already': True})
        # La decisión se registra a nombre de quien decide: el usuario con
        # sesión iniciada o, desde el enlace público, el aprobador destinatario
        # (nunca el «Public user»).
        decider = request.env.user
        if decider._is_public() and req.approver_id:
            decider = req.approver_id
        req_as = req.with_user(decider).sudo()
        try:
            if action == 'reject':
                if not (rejection_reason or '').strip():
                    return self._render(req, {'action': 'reject',
                                              'done': False,
                                              'error': _("El motivo del "
                                                         "rechazo es obligatorio.")})
                req_as.action_reject(reason=rejection_reason)
            else:
                req_as.action_approve()
        except Exception as e:  # noqa: BLE001
            return self._render(req, {'action': action, 'done': False,
                                      'error': str(e)})
        return self._render(req, {'action': action, 'done': True})
