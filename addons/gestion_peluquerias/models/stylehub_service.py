# -*- coding: utf-8 -*-

from odoo import fields, models
from odoo.exceptions import UserError


class StylehubService(models.Model):
    _name = "stylehub.service"
    _description = "Servicio de Peluquería"
    _order = "name"
    _inherit = ['image.mixin']

    name = fields.Char(string="Nombre del Servicio", required=True)
    description = fields.Text(string="Descripción")
    price = fields.Float(string="Precio Base (€)", required=True)
    duration = fields.Float(
        string="Duración (horas)",
        required=True,
        help="Duración del servicio en horas decimales. Ej: 0.5 = 30 min, 1.5 = 1h 30min",
    )
    active = fields.Boolean(string="Activo", default=True)

    # Constraints
    _check_price = models.Constraint(
        'CHECK(price >= 0)',
        'El precio del servicio no puede ser negativo.',
    )
    _check_duration = models.Constraint(
        'CHECK(duration > 0)',
        'La duración del servicio debe ser estrictamente positiva.',
    )
    _unique_service_name = models.Constraint(
        'UNIQUE(name)',
        'Ya existe un servicio con ese nombre.',
    )

    def action_archive(self):
        for rec in self:
            active_lines = self.env['stylehub.appointment.line'].search([
                ('service_id', '=', rec.id),
                ('appointment_id.state', 'in', ('draft', 'confirmed')),
            ])
            if active_lines:
                appointments = active_lines.mapped('appointment_id')
                raise UserError(
                    "No se puede archivar el servicio '%s' porque está siendo "
                    "utilizado en %d cita(s) en curso (Borrador o Confirmada):\n%s\n\n"
                    "Cancela o finaliza esas citas antes de archivar el servicio."
                    % (
                        rec.name,
                        len(appointments),
                        '\n'.join('  - ' + a.name for a in appointments),
                    )
                )
        return super().action_archive()
