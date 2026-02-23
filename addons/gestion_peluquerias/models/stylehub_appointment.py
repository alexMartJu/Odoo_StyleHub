# -*- coding: utf-8 -*-

# =============================================================================
# MODELOS: stylehub.appointment y stylehub.appointment.line
# =============================================================================
# stylehub.appointment
#   Representa una cita de cliente en la peluquería. Es el núcleo del módulo.
#   Cada cita tiene un cliente, un estilista, una fecha/hora de inicio y
#   una o varias líneas de servicio.
#
# stylehub.appointment.line
#   Cada línea corresponde a un servicio incluido en la cita (corte, tinte…).
#   La suma de las duraciones de las líneas determina la hora de fin de la cita.
#
# FLUJO DE ESTADOS:
#   Borrador (draft) → Confirmada (confirmed) → Realizada (done)
#                                             ↘ Cancelada (cancelled)
#
# VALIDACIONES CLAVE:
#   - Anti-solape: el mismo estilista no puede tener dos citas solapadas.
#   - Horario comercial: las citas deben caber dentro del horario configurado.
#   - No citas en el pasado (para estados activos).
#   - Al menos un servicio por cita.
# =============================================================================

from datetime import timedelta
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_is_zero


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
    # Las citas más recientes aparecen primero en los listados
    _order = "date_start desc"

    # -------------------------------------------------------------------------
    # Campos básicos
    # -------------------------------------------------------------------------
    # Referencia única generada automáticamente: "Cita - Nombre - DD/MM/YYYY HH:MM"
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
        # Solo muestra estilistas activos en el selector del formulario
        domain=[('active', '=', True)],
    )
    date_start = fields.Datetime(
        string="Fecha y Hora de Inicio", required=True,
    )
    # La hora de fin NO se introduce manualmente; se calcula sumando
    # las duraciones de todos los servicios de la cita.
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
    # One2many: cada cita puede tener múltiples servicios (corte + tinte +…).
    # La suma de sus duraciones y precios calcula los totales de la cita.
    line_ids = fields.One2many(
        'stylehub.appointment.line', 'appointment_id', string="Servicios",
    )

    # -------------------------------------------------------------------------
    # Campos computados de totales
    # -------------------------------------------------------------------------
    # Ambos campos se recalculan automáticamente cuando cambia cualquier
    # línea de servicio (duración o precio).
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
    # Campo relacionado: obtiene el valor de is_frequent_client del cliente
    # sin necesitar cálculo adicional. store=False porque es solo informativo.
    is_vip_client = fields.Boolean(
        string="Cliente VIP",
        related='partner_id.is_frequent_client',
        store=False,
    )
    # Descuento del 5% aplicado si el cliente ya tenía 5+ citas realizadas
    # con fecha ANTERIOR a ésta (el descuento se aplica desde la 6ª cita).
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
    # Máquina de estados con 4 valores posibles.
    # copy=False: al duplicar una cita el estado siempre empieza en 'draft'.
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
        """
        Genera automáticamente la referencia de la cita con el formato:
        "Cita - <nombre del cliente> - <fecha y hora local>"

        Usa context_timestamp() para convertir la fecha UTC almacenada en
        PostgreSQL a la hora local del usuario, evitando mostrar UTC en el UI.
        """
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
        """
        Suma la duración (horas) y el precio de todas las líneas de servicio.
        Se recalcula cada vez que se añade, edita o elimina una línea.
        """
        for rec in self:
            rec.total_duration = sum(rec.line_ids.mapped('duration'))
            rec.total_amount = sum(rec.line_ids.mapped('price_unit'))

    @api.depends('date_start', 'total_duration')
    def _compute_date_end(self):
        """
        Calcula la fecha y hora de fin sumando la duración total a la de inicio.
        Si no hay servicios, date_end es igual a date_start.
        Este campo es el que usa la vista de Calendario para dibujar el bloque
        de la cita con la longitud correcta.
        """
        for rec in self:
            if rec.date_start and rec.total_duration:
                rec.date_end = rec.date_start + timedelta(hours=rec.total_duration)
            else:
                rec.date_end = rec.date_start

    @api.depends('total_amount', 'partner_id.appointment_ids.state', 'date_start')
    def _compute_discount(self):
        """
        Calcula el descuento VIP (5%) y el importe final.

        Lógica de descuento:
          - El cliente debe tener 5 o más citas 'Realizadas' (done)
            con fecha de inicio ANTERIOR a la cita actual.
          - Esto asegura que el descuento se aplica a partir de la 6ª cita,
            no retroactivamente sobre citas anteriores.
        """
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

            if applies_discount and not float_is_zero(rec.total_amount, precision_digits=2):
                rec.discount_amount = rec.total_amount * 0.05
            else:
                rec.discount_amount = 0.0
            rec.final_amount = rec.total_amount - rec.discount_amount

    # -------------------------------------------------------------------------
    # Restricciones / Constraints
    # -------------------------------------------------------------------------
    @api.constrains('date_start')
    def _check_date_start_not_in_past(self):
        """
        No se puede crear ni modificar una cita programada (borrador o confirmada)
        con fecha y hora de inicio en el pasado.
        Las citas ya realizadas o canceladas quedan exentas de esta regla.
        """
        now = fields.Datetime.now()
        for rec in self:
            if rec.state in ('draft', 'confirmed') and rec.date_start and rec.date_start < now:
                start_local = fields.Datetime.context_timestamp(rec, rec.date_start)
                raise ValidationError(
                    "No se puede programar una cita en el pasado.\n\n"
                    "La fecha y hora de inicio seleccionada (%s) ya ha pasado.\n"
                    "Por favor, elige una fecha y hora futura."
                    % start_local.strftime('%d/%m/%Y %H:%M')
                )

    @api.constrains('line_ids')
    def _check_has_services(self):
        """Una cita debe tener al menos un servicio."""
        for rec in self:
            if not rec.line_ids:
                raise ValidationError(
                    "La cita '%s' no tiene ningún servicio seleccionado. "
                    "Añade al menos un servicio antes de guardar."
                    % rec.name
                )

    @api.constrains('stylist_id', 'date_start', 'date_end', 'state', 'line_ids')
    def _check_stylist_overlap(self):
        """
        Impide guardar una cita si el estilista ya tiene otra cita que se
        solapa en el mismo rango de tiempo.

        Algoritmo de detección de solapamiento:
          Dos intervalos [A_start, A_end) y [B_start, B_end) se solapan si:
            A_start < B_end  AND  A_end > B_start
          Esta es la condición estándar para detectar solapamiento de intervalos.
        """
        for rec in self:
            # Las citas canceladas no bloquean la agenda
            if rec.state == 'cancelled':
                continue
            if not rec.stylist_id or not rec.date_start or not rec.date_end:
                continue
            # Buscar citas del mismo estilista que se solapen en horario.
            # El dominio usa la fórmula de solapamiento de intervalos:
            # date_start < rec.date_end  AND  date_end > rec.date_start
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

    @api.constrains('date_start', 'date_end', 'line_ids')
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
    # Los métodos públicos (sin prefijo _) pueden ser llamados desde botones
    # en las vistas XML mediante type="object".
    # Iterar sobre 'self' permite que el botón funcione también en modo lista.
    def action_confirm(self):
        """Pasa la cita de 'Borrador' a 'Confirmada'."""
        for rec in self:
            if rec.state != 'draft':
                raise UserError("Solo se pueden confirmar citas en estado 'Borrador'.")
            rec.state = 'confirmed'
        return True

    def action_done(self):
        """Pasa la cita de 'Confirmada' a 'Realizada'."""
        for rec in self:
            if rec.state != 'confirmed':
                raise UserError("Solo se pueden finalizar citas en estado 'Confirmada'.")
            rec.state = 'done'
        return True

    def action_cancel(self):
        """Cancela la cita. No se puede cancelar si ya está realizada o cancelada."""
        for rec in self:
            if rec.state in ('done', 'cancelled'):
                raise UserError("No se puede cancelar una cita ya realizada o cancelada.")
            rec.state = 'cancelled'
        return True


class StylehubAppointmentLine(models.Model):
    """
    Cada registro representa un servicio dentro de una cita.
    Ejemplos: Corte, Tinte, Peinado…

    La duración y el precio se copian automáticamente del servicio
    seleccionado (via onchange), pero pueden editarse manualmente.
    La suma de todas las líneas determina la duración total y el
    subtotal de la cita padre.
    """
    _name = "stylehub.appointment.line"
    _description = "Línea de Servicio de Cita"
    _order = "id"   # Mantener el orden de inserción

    # ondelete='cascade': si se borra la cita, se borran también sus líneas
    appointment_id = fields.Many2one(
        'stylehub.appointment', string="Cita", required=True, ondelete='cascade',
    )
    service_id = fields.Many2one(
        'stylehub.service', string="Servicio", required=True,
    )
    # Precio editable: se rellena automáticamente con el precio del servicio,
    # pero la gerente puede modificarlo en el momento (ej: recargo por volumen)
    price_unit = fields.Float(
        string="Precio (€)",
        help="Precio editable. Se rellena automáticamente al elegir el servicio.",
    )
    # Duración en horas decimales (0.5 = 30 min, 1.5 = 1h 30min…)
    duration = fields.Float(
        string="Duración (horas)",
        help="Se rellena automáticamente al elegir el servicio.",
    )

    # -------------------------------------------------------------------------
    # Onchange: al seleccionar un servicio, rellenar precio y duración
    # -------------------------------------------------------------------------
    @api.onchange('service_id')
    def _onchange_service_id(self):
        """
        Se ejecuta en tiempo real en el navegador (sin guardar en BBDD)
        cuando el usuario selecciona o cambia el servicio en una línea.

        Rellena automáticamente price_unit y duration con los valores del
        servicio elegido. El usuario puede cambiarlos manualmente después.
        Si se borra el servicio, los campos vuelven a cero.
        """
        if self.service_id:
            self.price_unit = self.service_id.price
            self.duration = self.service_id.duration
        else:
            self.price_unit = 0.0
            self.duration = 0.0

    # -------------------------------------------------------------------------
    # Constraints SQL: validación a nivel de base de datos
    # -------------------------------------------------------------------------
    _check_line_price = models.Constraint(
        'CHECK(price_unit >= 0)',
        'El precio de la línea no puede ser negativo.',
    )
    _check_line_duration = models.Constraint(
        'CHECK(duration > 0)',
        'La duración de la línea debe ser positiva.',
    )
