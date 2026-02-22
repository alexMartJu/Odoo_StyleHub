# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # -------------------------------------------------------------------------
    # Relación inversa con las citas
    # -------------------------------------------------------------------------
    appointment_ids = fields.One2many(
        'stylehub.appointment', 'partner_id', string='Citas',
    )

    # -------------------------------------------------------------------------
    # Campos computados para la detección de clientes frecuentes (VIP)
    # -------------------------------------------------------------------------
    appointment_done_count = fields.Integer(
        string="Citas Realizadas",
        compute="_compute_appointment_done_count",
        store=True,
    )
    is_frequent_client = fields.Boolean(
        string="Cliente Frecuente (VIP)",
        compute="_compute_appointment_done_count",
        store=True,
        help="Marcado automáticamente cuando el cliente tiene más de 5 citas realizadas.",
    )

    @api.depends('appointment_ids.state')
    def _compute_appointment_done_count(self):
        for partner in self:
            done_count = len(
                partner.appointment_ids.filtered(lambda a: a.state == 'done')
            )
            partner.appointment_done_count = done_count
            partner.is_frequent_client = done_count > 5

    def action_archive(self):
        for partner in self:
            active_appointments = partner.appointment_ids.filtered(
                lambda a: a.state in ('draft', 'confirmed')
            )
            if active_appointments:
                raise UserError(
                    "No se puede archivar al cliente '%s' porque tiene "
                    "%d cita(s) en curso (Borrador o Confirmada):\n%s\n\n"
                    "Cancela esas citas antes de archivar al cliente."
                    % (
                        partner.name,
                        len(active_appointments),
                        '\n'.join('  - ' + a.name for a in active_appointments),
                    )
                )
        return super().action_archive()
