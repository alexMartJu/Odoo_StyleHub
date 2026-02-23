# -*- coding: utf-8 -*-

# =============================================================================
# MODELO: stylehub.stylist — Empleados / Estilistas de la Peluquería
# =============================================================================
# Gestiona el equipo de trabajo de StyleHub. Cada registro representa un
# estilista (peluquero/a). Las citas siempre van asignadas a uno de ellos.
#
# El campo 'active' (heredado del mixin de Odoo) permite archivar estilistas
# que ya no trabajan en el salón sin necesidad de eliminar sus registros
# históricos (citas pasadas, etc.).
#
# Hereda 'image.mixin' para poder adjuntar fotografía al estilista.
# =============================================================================

from odoo import fields, models
from odoo.exceptions import UserError


class StylehubStylist(models.Model):
    _name = "stylehub.stylist"
    _description = "Estilista de Peluquería"
    _order = "name"              # Lista ordenada alfabéticamente por nombre
    _inherit = ['image.mixin']   # Permite adjuntar foto al estilista

    # -------------------------------------------------------------------------
    # Datos personales del estilista
    # -------------------------------------------------------------------------
    name = fields.Char(string="Nombre", required=True)
    # active es un campo reservado de Odoo: cuando es False el registro se
    # oculta de las búsquedas normales (queda "archivado") pero no se borra
    active = fields.Boolean(
        string="Activo",
        default=True,
        help="Desmarcar para archivar al estilista sin eliminarlo.",
    )
    phone = fields.Char(string="Teléfono")
    email = fields.Char(string="Email")

    # -------------------------------------------------------------------------
    # Relaciones
    # -------------------------------------------------------------------------
    # One2many inverso: permite ver desde el formulario del estilista
    # todas las citas que tiene asignadas
    appointment_ids = fields.One2many(
        'stylehub.appointment', 'stylist_id', string='Citas'
    )

    # -------------------------------------------------------------------------
    # Restricciones SQL
    # -------------------------------------------------------------------------
    # Evita que haya dos estilistas con el mismo nombre en la base de datos
    _unique_stylist_name = models.Constraint(
        'UNIQUE(name)',
        'Ya existe un estilista con ese nombre.',
    )

    # -------------------------------------------------------------------------
    # Sobreescritura de action_archive (botón "Archivar")
    # -------------------------------------------------------------------------
    def action_archive(self):
        """
        Impide archivar a un estilista mientras tenga citas pendientes
        (en estado 'Borrador' o 'Confirmada').

        Motivo: si se archivara el estilista, sus citas futuras quedarían
        sin un responsable válido, lo que dejaría desatendidos a los clientes.
        La gerencia debe cancelar o reasignar esas citas primero.
        """
        for rec in self:
            # Filtrar solo las citas activas (no realizadas ni canceladas)
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
        # Si no hay citas activas, proceder con el archivado estándar de Odoo
        return super().action_archive()
