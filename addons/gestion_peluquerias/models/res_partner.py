# -*- coding: utf-8 -*-

# =============================================================================
# MODELO: res.partner (herencia) — Extensión del Cliente de Odoo
# =============================================================================
# Odoo ya dispone del modelo res.partner para gestionar clientes, proveedores
# y contactos en general. En lugar de crear un modelo de cliente propio,
# extendemos el existente añadiendo:
#
#   1. Una relación inversa con las citas de StyleHub.
#   2. Un contador de citas «Realizadas» y un indicador VIP calculados
#      automáticamente.
#
# Gracias a la herencia (_inherit), estos campos nuevos conviven con todos
# los campos estándar de res.partner (nombre, teléfono, email, dirección…).
# =============================================================================

from odoo import api, fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    # _inherit indica que estamos EXTENDIENDO el modelo existente res.partner,
    # NO creando uno nuevo. Los cambios se aplican sobre la misma tabla SQL.
    _inherit = 'res.partner'

    # -------------------------------------------------------------------------
    # Relación inversa con las citas
    # -------------------------------------------------------------------------
    # One2many: desde la ficha del cliente podemos ver todas sus citas.
    # El campo 'partner_id' en stylehub.appointment es el lado Many2one.
    appointment_ids = fields.One2many(
        'stylehub.appointment', 'partner_id', string='Citas',
    )

    # -------------------------------------------------------------------------
    # Campos computados para la detección de clientes frecuentes (VIP)
    # -------------------------------------------------------------------------
    # store=True: el valor se almacena en BBDD y no se recalcula en cada
    # lectura, lo que mejora el rendimiento en listados grandes.
    appointment_done_count = fields.Integer(
        string="Citas Realizadas",
        compute="_compute_appointment_done_count",
        store=True,
    )
    # Bandera VIP: True cuando el cliente supera las 5 citas realizadas.
    # Se usa en la vista del formulario para mostrar el distintivo «⭐ Cliente VIP».
    is_frequent_client = fields.Boolean(
        string="Cliente Frecuente (VIP)",
        compute="_compute_appointment_done_count",
        store=True,
        help="Marcado automáticamente cuando el cliente tiene más de 5 citas realizadas.",
    )

    @api.depends('appointment_ids.state')
    def _compute_appointment_done_count(self):
        """
        Calcula cuántas citas en estado 'Realizada' (done) tiene el cliente
        y determina si es VIP (más de 5 citas realizadas).

        Se dispara automáticamente cada vez que cambia el estado de cualquiera
        de las citas del cliente gracias al decorator @api.depends.
        """
        for partner in self:
            # Contamos solo las citas que ya han sido completadas (estado 'done')
            done_count = len(
                partner.appointment_ids.filtered(lambda a: a.state == 'done')
            )
            partner.appointment_done_count = done_count
            # Un cliente se convierte en VIP al superar las 5 citas realizadas
            partner.is_frequent_client = done_count > 5

    # -------------------------------------------------------------------------
    # Sobreescritura de action_archive (botón "Archivar")
    # -------------------------------------------------------------------------
    def action_archive(self):
        """
        Impide archivar a un cliente si tiene citas pendientes.

        Motivo: archivar al cliente ocultaría sus citas activas del sistema,
        dejando al estilista sin información de agenda para esa cita.
        """
        for partner in self:
            # Filtrar las citas del cliente que siguen activas
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
        # Sin citas activas, ejecutar el archivado estándar de Odoo
        return super().action_archive()
