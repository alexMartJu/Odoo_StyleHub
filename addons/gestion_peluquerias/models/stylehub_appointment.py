# -*- coding: utf-8 -*-

from datetime import timedelta
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


def _float_to_time_str(value):
    """Convierte un float de horas (ej: 9.5) a cadena 'HH:MM' (ej: '09:30')."""
    hours = int(value)
    minutes = round((value % 1) * 60)
    return "%02d:%02d" % (hours, minutes)


def _make_time(dt, float_hours):
    """Devuelve un datetime con la hora indicada por float_hours sobre la fecha de dt."""
    hours = int(float_hours)
    minutes = round((float_hours % 1) * 60)
    return dt.replace(hour=hours, minute=minutes, second=0, microsecond=0)


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
        Valida que la cita esté dentro del horario comercial configurado en
        stylehub.schedule. Si no existe ninguna configuración de horario,
        la validación se omite para no bloquear el sistema.
        """
        _WEEKDAY_NAMES = {
            0: 'lunes', 1: 'martes', 2: 'miércoles',
            3: 'jueves', 4: 'viernes', 5: 'sábado', 6: 'domingo',
        }

        # Si no hay horario configurado, bloquear la creación de citas
        schedule = self.env['stylehub.schedule'].search([], limit=1)
        if not schedule:
            raise ValidationError(
                "⚠️ No se ha configurado el horario de la peluquería.\n\n"
                "Antes de crear citas, ve a "
                "StyleHub → Configuración → Horario "
                "y crea la configuración de horario. "
                "Las citas solo pueden crearse dentro del horario definido."
            )

        for rec in self:
            if not rec.date_start or not rec.date_end:
                continue

            # Convertir UTC → hora local del usuario
            start = fields.Datetime.context_timestamp(rec, rec.date_start)
            end   = fields.Datetime.context_timestamp(rec, rec.date_end)
            weekday = start.weekday()  # 0 = Lunes, 6 = Domingo

            # ── Domingo: siempre cerrado ──────────────────────────────────────
            if weekday == 6:
                raise ValidationError(
                    "La peluquería no abre los domingos. "
                    "Por favor, elige otro día para la cita."
                )

            # ── Sábado ───────────────────────────────────────────────────────
            if weekday == 5:
                if not schedule.saturday_active:
                    raise ValidationError(
                        "La peluquería no abre los sábados según la "
                        "configuración de horario actual."
                    )
                open_sat_morn  = _make_time(start, schedule.saturday_morning_open)
                close_sat_morn = _make_time(start, schedule.saturday_morning_close)
                in_sat_morning = open_sat_morn <= start and end <= close_sat_morn

                in_sat_afternoon = False
                if schedule.saturday_afternoon_active:
                    open_sat_aft  = _make_time(start, schedule.saturday_afternoon_open)
                    close_sat_aft = _make_time(start, schedule.saturday_afternoon_close)
                    in_sat_afternoon = open_sat_aft <= start and end <= close_sat_aft

                if not in_sat_morning and not in_sat_afternoon:
                    if schedule.saturday_afternoon_active:
                        raise ValidationError(
                            "El sábado la peluquería abre de %s a %s "
                            "y de %s a %s. "
                            "La cita solicitada (%s – %s) está fuera de este horario."
                            % (
                                _float_to_time_str(schedule.saturday_morning_open),
                                _float_to_time_str(schedule.saturday_morning_close),
                                _float_to_time_str(schedule.saturday_afternoon_open),
                                _float_to_time_str(schedule.saturday_afternoon_close),
                                start.strftime('%H:%M'),
                                end.strftime('%H:%M'),
                            )
                        )
                    else:
                        raise ValidationError(
                            "El sábado la peluquería abre de %s a %s. "
                            "La cita solicitada (%s – %s) está fuera de este horario."
                            % (
                                _float_to_time_str(schedule.saturday_morning_open),
                                _float_to_time_str(schedule.saturday_morning_close),
                                start.strftime('%H:%M'),
                                end.strftime('%H:%M'),
                            )
                        )
                continue

            # ── Lunes a Viernes ───────────────────────────────────────────────
            open_morning    = _make_time(start, schedule.weekday_morning_open)
            close_morning   = _make_time(start, schedule.weekday_morning_close)
            open_afternoon  = _make_time(start, schedule.weekday_afternoon_open)
            close_afternoon = _make_time(start, schedule.weekday_afternoon_close)

            in_morning   = open_morning   <= start and end <= close_morning
            in_afternoon = open_afternoon <= start and end <= close_afternoon

            if not in_morning and not in_afternoon:
                raise ValidationError(
                    "De lunes a viernes la peluquería abre de %s a %s "
                    "y de %s a %s. "
                    "La cita del %s (%s – %s) cae fuera del horario "
                    "comercial o se solapa con el descanso de mediodía."
                    % (
                        _float_to_time_str(schedule.weekday_morning_open),
                        _float_to_time_str(schedule.weekday_morning_close),
                        _float_to_time_str(schedule.weekday_afternoon_open),
                        _float_to_time_str(schedule.weekday_afternoon_close),
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
