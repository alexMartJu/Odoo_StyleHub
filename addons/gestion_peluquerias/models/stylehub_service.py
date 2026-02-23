# -*- coding: utf-8 -*-

# =============================================================================
# MODELO: stylehub.service — Catálogo de Servicios de Peluquería
# =============================================================================
# Almacena los servicios que ofrece la peluquería (corte, tinte, etc.).
# Cada servicio tiene un precio base y una duración en horas decimales.
# La duración es fundamental para calcular automáticamente la hora de fin
# de cada cita y para validar el horario comercial.
#
# Hereda 'image.mixin' para poder asociar una imagen/foto al servicio.
# =============================================================================

from odoo import fields, models
from odoo.exceptions import UserError


class StylehubService(models.Model):
    _name = "stylehub.service"
    _description = "Servicio de Peluquería"
    _order = "name"              # Los servicios se ordenan alfabéticamente
    _inherit = ['image.mixin']   # Permite adjuntar imagen al servicio

    # -------------------------------------------------------------------------
    # Campos del catálogo
    # -------------------------------------------------------------------------
    name = fields.Char(string="Nombre del Servicio", required=True)
    description = fields.Text(string="Descripción")
    price = fields.Float(string="Precio Base (€)", required=True)
    duration = fields.Float(
        string="Duración (horas)",
        required=True,
        # Usa horas decimales: 0.5 = 30 min, 1.5 = 1 h 30 min, 2.0 = 2 h
        help="Duración del servicio en horas decimales. Ej: 0.5 = 30 min, 1.5 = 1h 30min",
    )
    # Campo reservado de Odoo: permite archivar/desarchivar sin borrar el registro
    active = fields.Boolean(string="Activo", default=True)

    # -------------------------------------------------------------------------
    # Restricciones SQL (validadas directamente en la base de datos)
    # -------------------------------------------------------------------------
    # Estas constraints se comprueban a nivel de BBDD, por lo que son más
    # eficientes que las Python constraints para valores simples.
    _check_price = models.Constraint(
        'CHECK(price >= 0)',
        'El precio del servicio no puede ser negativo.',
    )
    _check_duration = models.Constraint(
        'CHECK(duration > 0)',
        'La duración del servicio debe ser estrictamente positiva.',
    )
    # Garantiza que no haya dos servicios con el mismo nombre
    _unique_service_name = models.Constraint(
        'UNIQUE(name)',
        'Ya existe un servicio con ese nombre.',
    )

    # -------------------------------------------------------------------------
    # Sobreescritura de action_archive (botón "Archivar")
    # -------------------------------------------------------------------------
    def action_archive(self):
        """
        Impide archivar un servicio si está siendo usado en citas activas
        (en estado 'Borrador' o 'Confirmada').

        Motivo: si archiváramos el servicio, las citas en curso quedarían
        con una línea apuntando a un servicio inactivo, lo que genera
        incoherencias en los cálculos de duración y precio.
        """
        for rec in self:
            # Buscar líneas de cita que usen este servicio y cuya cita esté activa
            active_lines = self.env['stylehub.appointment.line'].search([
                ('service_id', '=', rec.id),
                ('appointment_id.state', 'in', ('draft', 'confirmed')),
            ])
            if active_lines:
                # Obtener las citas únicas afectadas para mostrarlas en el error
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
        # Si no hay citas activas, ejecutar el archivado estándar de Odoo
        return super().action_archive()
