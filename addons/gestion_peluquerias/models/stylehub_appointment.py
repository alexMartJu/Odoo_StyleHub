# -*- coding: utf-8 -*-

from datetime import timedelta
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class StylehubAppointment(models.Model):
    _name = "stylehub.appointment"
    _description = "Cita de Peluquería"
    _order = "date_start desc"

    # -------------------------------------------------------------------------
    # Campos básicos
    # -------------------------------------------------------------------------
    name = fields.Char(
        string="Referencia",
        compute="_compute_name",
        store=True,
    )
    partner_id = fields.Many2one(
        'res.partner', string="Cliente", required=True,
    )
    stylist_id = fields.Many2one(
        'stylehub.stylist', string="Estilista", required=True,
        domain=[('active', '=', True)],
    )
    date_start = fields.Datetime(
        string="Fecha y Hora de Inicio", required=True,
    )
    date_end = fields.Datetime(
        string="Fecha y Hora de Fin",
        compute="_compute_date_end",
        store=True,
        help="Calculada automáticamente sumando las duraciones de los servicios.",
    )
    notes = fields.Text(string="Notas internas")

    # -------------------------------------------------------------------------
    # Líneas de servicios
    # -------------------------------------------------------------------------
    line_ids = fields.One2many(
        'stylehub.appointment.line', 'appointment_id', string="Servicios",
    )

    # -------------------------------------------------------------------------
    # Campos computados de totales
    # -------------------------------------------------------------------------
    total_duration = fields.Float(
        string="Duración Total (horas)",
        compute="_compute_totals",
        store=True,
    )
    total_amount = fields.Float(
        string="Subtotal (€)",
        compute="_compute_totals",
        store=True,
    )

    # -------------------------------------------------------------------------
    # Descuento VIP
    # -------------------------------------------------------------------------
    is_vip_client = fields.Boolean(
        string="Cliente VIP",
        related='partner_id.is_frequent_client',
        store=False,
    )
    discount_amount = fields.Float(
        string="Descuento VIP 5% (€)",
        compute="_compute_discount",
        store=True,
        help="Descuento del 5% aplicado automáticamente a clientes frecuentes (VIP).",
    )
    final_amount = fields.Float(
        string="Total a Pagar (€)",
        compute="_compute_discount",
        store=True,
        help="Total a pagar tras aplicar el descuento VIP si corresponde.",
    )

    # -------------------------------------------------------------------------
    # Estado / flujo de trabajo
    # -------------------------------------------------------------------------
    state = fields.Selection(
        [
            ('draft', 'Borrador'),
            ('confirmed', 'Confirmada'),
            ('done', 'Realizada'),
            ('cancelled', 'Cancelada'),
        ],
        string="Estado",
        required=True,
        copy=False,
        default='draft',
    )

    # -------------------------------------------------------------------------
    # Campos computados
    # -------------------------------------------------------------------------
    @api.depends('partner_id', 'date_start')
    def _compute_name(self):
        for rec in self:
            if rec.partner_id and rec.date_start:
                # Convertir UTC → hora local del usuario antes de formatear
                start_local = fields.Datetime.context_timestamp(rec, rec.date_start)
                rec.name = "Cita - %s - %s" % (
                    rec.partner_id.name,
                    start_local.strftime('%d/%m/%Y %H:%M'),
                )
            elif rec.partner_id:
                rec.name = "Cita - %s" % rec.partner_id.name
            else:
                rec.name = "Nueva Cita"

    @api.depends('line_ids.duration', 'line_ids.price_unit')
    def _compute_totals(self):
        for rec in self:
            rec.total_duration = sum(rec.line_ids.mapped('duration'))
            rec.total_amount = sum(rec.line_ids.mapped('price_unit'))

    @api.depends('date_start', 'total_duration')
    def _compute_date_end(self):
        for rec in self:
            if rec.date_start and rec.total_duration:
                rec.date_end = rec.date_start + timedelta(hours=rec.total_duration)
            else:
                rec.date_end = rec.date_start

    @api.depends('total_amount', 'partner_id.appointment_ids.state', 'date_start')
    def _compute_discount(self):
        Appointment = self.env['stylehub.appointment']
        for rec in self:
            applies_discount = False
            if rec.partner_id and rec.date_start:
                # Contamos cuántas citas 'Realizadas' tenía el cliente
                # con fecha de inicio ANTERIOR a esta cita concreta.
                # El descuento se aplica a partir de la 6ª cita,
                # es decir, cuando ya tiene 5 o más realizadas previas.
                prior_done = Appointment.search_count([
                    ('partner_id', '=', rec.partner_id.id),
                    ('state', '=', 'done'),
                    ('date_start', '<', rec.date_start),
                ])
                applies_discount = prior_done >= 5

            if applies_discount:
                rec.discount_amount = rec.total_amount * 0.05
            else:
                rec.discount_amount = 0.0
            rec.final_amount = rec.total_amount - rec.discount_amount

    # -------------------------------------------------------------------------
    # Restricciones / Constraints
    # -------------------------------------------------------------------------
    @api.constrains('stylist_id', 'date_start', 'date_end', 'state')
    def _check_stylist_overlap(self):
        for rec in self:
            # Las citas canceladas no bloquean la agenda
            if rec.state == 'cancelled':
                continue
            if not rec.stylist_id or not rec.date_start or not rec.date_end:
                continue
            # Buscar citas del mismo estilista que se solapen en horario
            domain = [
                ('stylist_id', '=', rec.stylist_id.id),
                ('state', '!=', 'cancelled'),
                ('id', '!=', rec.id),
                ('date_start', '<', rec.date_end),
                ('date_end', '>', rec.date_start),
            ]
            overlap = self.search_count(domain)
            if overlap > 0:
                start_local = fields.Datetime.context_timestamp(rec, rec.date_start)
                end_local   = fields.Datetime.context_timestamp(rec, rec.date_end)
                raise ValidationError(
                    "¡CONFLICTO DE HORARIO! El estilista '%s' ya tiene una cita "
                    "que se solapa con el horario %s - %s. "
                    "Por favor, elige otro horario o estilista."
                    % (
                        rec.stylist_id.name,
                        start_local.strftime('%d/%m/%Y %H:%M'),
                        end_local.strftime('%d/%m/%Y %H:%M'),
                    )
                )

    @api.constrains('date_start', 'date_end')
    def _check_business_hours(self):
        """
        Valida que la cita esté dentro del horario comercial de StyleHub:
          - Lunes a Viernes: 9:30 - 13:30 y 16:30 - 20:30
          - Sábado:          9:30 - 14:00
          - Domingo:         cerrado
        Los Datetime se almacenan en UTC en Odoo; aquí trabajamos directamente
        con los valores introducidos (sin conversión de zona horaria) para
        mantener la simplicidad del módulo.
        """
        # Días de la semana (0 = Lunes, 6 = Domingo)
        _WEEKDAY_NAMES = {
            0: 'lunes', 1: 'martes', 2: 'miércoles',
            3: 'jueves', 4: 'viernes', 5: 'sábado', 6: 'domingo',
        }

        for rec in self:
            if not rec.date_start or not rec.date_end:
                continue

            # ── Convertir UTC --> hora lcoal del usuario ──────────────────────
            start = fields.Datetime.context_timestamp(rec, rec.date_start)
            end = fields.Datetime.context_timestamp(rec, rec.date_end)
            weekday = start.weekday()  # 0 = Lunes, 6 = Domingo

            # ── Domingo: cerrado ──────────────────────────────────────────────
            if weekday == 6:
                raise ValidationError(
                    "StyleHub no abre los domingos. "
                    "Por favor, elige otro día para la cita."
                )

            # ── Sábado: 9:30 – 14:00 ─────────────────────────────────────────
            if weekday == 5:
                open_sat = start.replace(hour=9,  minute=30, second=0, microsecond=0)
                close_sat = start.replace(hour=14, minute=0,  second=0, microsecond=0)
                if start < open_sat or end > close_sat:
                    raise ValidationError(
                        "StyleHub solo abre los sábados de 9:30 a 14:00. "
                        "La cita solicitada (%s – %s) está fuera de este horario."
                        % (start.strftime('%H:%M'), end.strftime('%H:%M'))
                    )
                continue

            # ── Lunes a Viernes: 9:30 – 13:30 y 16:30 – 20:30 ───────────────
            open_morning    = start.replace(hour=9,  minute=30, second=0, microsecond=0)
            close_morning   = start.replace(hour=13, minute=30, second=0, microsecond=0)
            open_afternoon  = start.replace(hour=16, minute=30, second=0, microsecond=0)
            close_afternoon = start.replace(hour=20, minute=30, second=0, microsecond=0)

            in_morning   = open_morning   <= start and end <= close_morning
            in_afternoon = open_afternoon <= start and end <= close_afternoon

            if not in_morning and not in_afternoon:
                raise ValidationError(
                    "De lunes a viernes StyleHub abre de 9:30 a 13:30 "
                    "y de 16:30 a 20:30. "
                    "La cita del %s (%s – %s) cae fuera del horario "
                    "comercial o se solapa con el descanso de mediodía."
                    % (
                        _WEEKDAY_NAMES[weekday],
                        start.strftime('%H:%M'),
                        end.strftime('%H:%M'),
                    )
                )

    # -------------------------------------------------------------------------
    # Botones de acción / flujo de estados
    # -------------------------------------------------------------------------
    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError("Solo se pueden confirmar citas en estado 'Borrador'.")
            rec.state = 'confirmed'
        return True

    def action_done(self):
        for rec in self:
            if rec.state != 'confirmed':
                raise UserError("Solo se pueden finalizar citas en estado 'Confirmada'.")
            rec.state = 'done'
        return True

    def action_cancel(self):
        for rec in self:
            if rec.state == 'done':
                raise UserError("No se puede cancelar una cita ya realizada.")
            rec.state = 'cancelled'
        return True

    def action_reset_draft(self):
        for rec in self:
            if rec.state != 'cancelled':
                raise UserError("Solo se puede restablecer a borrador una cita cancelada.")
            rec.state = 'draft'
        return True


class StylehubAppointmentLine(models.Model):
    _name = "stylehub.appointment.line"
    _description = "Línea de Servicio de Cita"
    _order = "id"

    appointment_id = fields.Many2one(
        'stylehub.appointment', string="Cita", required=True, ondelete='cascade',
    )
    service_id = fields.Many2one(
        'stylehub.service', string="Servicio", required=True,
    )
    price_unit = fields.Float(
        string="Precio (€)",
        help="Precio editable. Se rellena automáticamente al elegir el servicio.",
    )
    duration = fields.Float(
        string="Duración (horas)",
        help="Se rellena automáticamente al elegir el servicio.",
    )

    # -------------------------------------------------------------------------
    # Onchange: al seleccionar un servicio, rellenar precio y duración
    # -------------------------------------------------------------------------
    @api.onchange('service_id')
    def _onchange_service_id(self):
        if self.service_id:
            self.price_unit = self.service_id.price
            self.duration = self.service_id.duration
        else:
            self.price_unit = 0.0
            self.duration = 0.0

    # -------------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------------
    _check_line_price = models.Constraint(
        'CHECK(price_unit >= 0)',
        'El precio de la línea no puede ser negativo.',
    )
    _check_line_duration = models.Constraint(
        'CHECK(duration > 0)',
        'La duración de la línea debe ser positiva.',
    )
