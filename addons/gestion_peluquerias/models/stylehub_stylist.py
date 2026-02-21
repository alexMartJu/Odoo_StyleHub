# -*- coding: utf-8 -*-

from odoo import fields, models


class StylehubStylist(models.Model):
    _name = "stylehub.stylist"
    _description = "Estilista de Peluquería"
    _order = "name"

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
