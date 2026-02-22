# -*- coding: utf-8 -*-

from odoo import fields, models
from odoo.exceptions import UserError


class StylehubStylist(models.Model):
    _name = "stylehub.stylist"
    _description = "Estilista de Peluquería"
    _order = "name"
    _inherit = ['image.mixin']

    name = fields.Char(string="Nombre", required=True)
    active = fields.Boolean(
        string="Activo",
        default=True,
        help="Desmarcar para archivar al estilista sin eliminarlo.",
    )
    phone = fields.Char(string="Teléfono")
    email = fields.Char(string="Email")

    # Relación inversa para saber cuántas citas tiene asignadas
    appointment_ids = fields.One2many(
        'stylehub.appointment', 'stylist_id', string='Citas'
    )

    # Constraints
    _unique_stylist_name = models.Constraint(
        'UNIQUE(name)',
        'Ya existe un estilista con ese nombre.',
    )

    def action_archive(self):
        for rec in self:
            active_appointments = rec.appointment_ids.filtered(
                lambda a: a.state in ('draft', 'confirmed')
            )
            if active_appointments:
                raise UserError(
                    "No se puede archivar al estilista '%s' porque tiene "
                    "%d cita(s) en curso (Borrador o Confirmada):\n%s\n\n"
                    "Cancela o reasigna esas citas antes de archivar al estilista."
                    % (
                        rec.name,
                        len(active_appointments),
                        '\n'.join('  - ' + a.name for a in active_appointments),
                    )
                )
        return super().action_archive()
