# -*- coding: utf-8 -*-

# =============================================================================
# MODELO: stylehub.schedule — Configuración de Horario de la Peluquería
# =============================================================================
# Almacena el único horario comercial de StyleHub.
#
# DISEÑO SINGLETON: solo puede existir UN registro de horario al mismo tiempo.
# La lógica en create() y unlink() lo garantiza.
#
# PROTECCIÓN DE EDICIÓN: mientras haya citas activas (Borrador o Confirmada)
# no se permite modificar el horario, ya que esas citas fueron validadas
# con el horario anterior y podrían quedar fuera de rango si se cambia.
#
# ESTRUCTURA DE TURNOS:
#   • Lunes – Viernes: turno de mañana + turno de tarde (ambos obligatorios).
#   • Sábado          : opcional; puede tener solo mañana o mañana + tarde.
#   • Domingo         : siempre cerrado (no hay campos para él).
# =============================================================================

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


def _float_to_time_str(value):
    """Convierte un float de horas (ej: 9.5) a cadena 'HH:MM' (ej: '09:30')."""
    hours = int(value)
    minutes = round((value % 1) * 60)
    return "%02d:%02d" % (hours, minutes)


class StylehubSchedule(models.Model):
    _name = "stylehub.schedule"
    _description = "Configuración de Horario de la Peluquería"

    # Nombre descriptivo del horario (campo obligatorio por convención de Odoo)
    name = fields.Char(
        string="Nombre del Horario",
        required=True,
        default="Horario de la Peluquería",
    )

    # -------------------------------------------------------------------------
    # Lunes a Viernes (mismo horario para todos los días laborables)
    # -------------------------------------------------------------------------
    # Los horarios se guardan como número decimal de horas.
    # Ejemplo: 9.5 = 09:30, 13.5 = 13:30, 20.5 = 20:30
    weekday_morning_open = fields.Float(
        string="Apertura mañana (L-V)",
        required=True,
        default=9.5,
        help="Hora de apertura del turno de mañana de lunes a viernes. "
             "Usa notación decimal: 9.5 = 09:30, 8.0 = 08:00. Mínimo: 8.0",
    )
    weekday_morning_close = fields.Float(
        string="Cierre mañana (L-V)",
        required=True,
        default=13.5,
        help="Hora de cierre del turno de mañana de lunes a viernes. "
             "Ej: 13.5 = 13:30.",
    )
    weekday_afternoon_open = fields.Float(
        string="Apertura tarde (L-V)",
        required=True,
        default=16.5,
        help="Hora de apertura del turno de tarde de lunes a viernes. "
             "Ej: 16.5 = 16:30.",
    )
    weekday_afternoon_close = fields.Float(
        string="Cierre tarde (L-V)",
        required=True,
        default=20.5,
        help="Hora de cierre del turno de tarde de lunes a viernes. "
             "Usa notación decimal: 20.5 = 20:30. Máximo: 22.0",
    )

    # -------------------------------------------------------------------------
    # Sábado
    # -------------------------------------------------------------------------
    # El sábado es opcional: si 'saturday_active' = False, no se validan
    # ni se muestran los campos de horario del sábado en el formulario.
    saturday_active = fields.Boolean(
        string="Abre el sábado",
        default=True,
        help="Marcar si la peluquería trabaja los sábados.",
    )
    saturday_morning_open = fields.Float(
        string="Apertura mañana (Sáb)",
        default=9.5,
        help="Hora de apertura del turno de mañana del sábado. "
             "Usa notación decimal: 9.5 = 09:30. Mínimo: 8.0",
    )
    saturday_morning_close = fields.Float(
        string="Cierre mañana (Sáb)",
        default=14.0,
        help="Hora de cierre del turno de mañana del sábado. "
             "Ej: 14.0 = 14:00.",
    )
    saturday_afternoon_active = fields.Boolean(
        string="Turno de tarde (Sáb)",
        default=False,
        # El sábado puede tener turno de tarde o no (muchas peluquerías solo abren mañana)
        help="Marcar si la peluquería también tiene turno de tarde los sábados.",
    )
    saturday_afternoon_open = fields.Float(
        string="Apertura tarde (Sáb)",
        default=16.5,
        help="Hora de apertura del turno de tarde del sábado. "
             "Ej: 16.5 = 16:30.",
    )
    saturday_afternoon_close = fields.Float(
        string="Cierre tarde (Sáb)",
        default=20.0,
        help="Hora de cierre del turno de tarde del sábado. "
             "Usa notación decimal: 20.0 = 20:00. Máximo: 22.0",
    )

    # -------------------------------------------------------------------------
    # Domingo: siempre cerrado (informativo)
    # -------------------------------------------------------------------------
    # No se definen campos de apertura/cierre para el domingo.

    # -------------------------------------------------------------------------
    # Campo computado: alerta de citas activas
    # -------------------------------------------------------------------------
    # Este campo se usa en la vista para mostrar una advertencia al usuario
    # informándole de que no puede editar el horario mientras haya citas activas.
    has_active_appointments = fields.Boolean(
        string="Tiene citas activas",
        compute="_compute_has_active_appointments",
        help="Indica si existen citas en estado 'Borrador' o 'Confirmada'. "
             "Mientras haya citas activas no se puede modificar el horario.",
    )

    @api.depends()
    def _compute_has_active_appointments(self):
        """
        Comprueba si existe alguna cita activa en el sistema.
        Al no depender de ningún campo específico (depends vacío),
        se recalcula cada vez que se accede al formulario de horario.
        """
        Appointment = self.env['stylehub.appointment']
        active_count = Appointment.search_count([
            ('state', 'in', ['draft', 'confirmed']),
        ])
        for rec in self:
            rec.has_active_appointments = active_count > 0

    # -------------------------------------------------------------------------
    # Patrón Singleton: solo puede existir 1 registro de horario
    # -------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        """
        Sobreescritura de create() para implementar el patrón singleton.
        Si ya existe un registro de horario, se bloquea la creación de otro.
        El decorador @api.model_create_multi es necesario en Odoo 17+ porque
        create() puede recibir una lista de diccionarios en lugar de uno solo.
        """
        if self.search_count([]) > 0:
            raise UserError(
                "Ya existe una configuración de horario.\n"
                "Solo puede haber una. Edite el registro existente "
                "desde el menú Configuración → Horario."
            )
        return super().create(vals_list)

    def unlink(self):
        """
        Impide eliminar el registro de horario.
        Eliminar el horario dejaría el sistema sin reglas de validación
        y bloquearía la creación de cualquier cita nueva.
        """
        raise UserError(
            "No está permitido eliminar la configuración de horario.\n"
            "Si necesitas cambiar los datos, edita el registro existente. "
            "Eliminar el horario podría dejar el sistema sin reglas de horario "
            "y es una operación irreversible."
        )

    def write(self, vals):
        """
        Impide modificar el horario mientras existan citas activas.

        Motivo: si se cambia el horario con citas ya programadas,
        esas citas podrían quedar fuera del nuevo rango horario,
        generando inconsistencias en la agenda.
        """
        Appointment = self.env['stylehub.appointment']
        active_count = Appointment.search_count([
            ('state', 'in', ['draft', 'confirmed']),
        ])
        if active_count > 0:
            raise UserError(
                "No se puede modificar el horario mientras existan citas en estado "
                "'Borrador' o 'Confirmada' (%d cita/s activa/s).\n"
                "Cancela o finaliza todas las citas activas antes de cambiar el horario."
                % active_count
            )
        return super().write(vals)

    # -------------------------------------------------------------------------
    # Python Constraints: validación de coherencia de los rangos horarios
    # -------------------------------------------------------------------------
    # Estas constraints se ejecutan en Python (servidor) y permiten mensajes
    # de error más descriptivos que las SQL constraints.
    # Se disparan automáticamente al guardar el registro si alguno de los
    # campos listados en @api.constrains ha cambiado.
    @api.constrains(
        'weekday_morning_open', 'weekday_morning_close',
        'weekday_afternoon_open', 'weekday_afternoon_close',
        'saturday_morning_open', 'saturday_morning_close',
        'saturday_afternoon_open', 'saturday_afternoon_close',
        'saturday_active', 'saturday_afternoon_active',
    )
    def _check_schedule_times(self):
        for rec in self:
            # ── Mínimo de apertura: 8:00 ─────────────────────────────────────
            if rec.weekday_morning_open < 8.0:
                raise ValidationError(
                    "La apertura de mañana (L-V) no puede ser antes de las 08:00. "
                    "Valor introducido: %s." % _float_to_time_str(rec.weekday_morning_open)
                )
            if rec.saturday_active and rec.saturday_morning_open < 8.0:
                raise ValidationError(
                    "La apertura de mañana del sábado no puede ser antes de las 08:00. "
                    "Valor introducido: %s." % _float_to_time_str(rec.saturday_morning_open)
                )
            if rec.saturday_active and rec.saturday_afternoon_active and rec.saturday_afternoon_open < 8.0:
                raise ValidationError(
                    "La apertura de tarde del sábado no puede ser antes de las 08:00. "
                    "Valor introducido: %s." % _float_to_time_str(rec.saturday_afternoon_open)
                )

            # ── Máximo de cierre: 22:00 ──────────────────────────────────────
            if rec.weekday_afternoon_close > 22.0:
                raise ValidationError(
                    "El cierre de tarde (L-V) no puede ser después de las 22:00. "
                    "Valor introducido: %s." % _float_to_time_str(rec.weekday_afternoon_close)
                )
            if rec.saturday_active and rec.saturday_morning_close > 22.0:
                raise ValidationError(
                    "El cierre de mañana del sábado no puede ser después de las 22:00. "
                    "Valor introducido: %s." % _float_to_time_str(rec.saturday_morning_close)
                )
            if rec.saturday_active and rec.saturday_afternoon_active and rec.saturday_afternoon_close > 22.0:
                raise ValidationError(
                    "El cierre de tarde del sábado no puede ser después de las 22:00. "
                    "Valor introducido: %s." % _float_to_time_str(rec.saturday_afternoon_close)
                )

            # ── Coherencia interna de los turnos (L-V) ───────────────────────
            # Cada turno: la apertura debe ser ANTES del cierre
            if rec.weekday_morning_open >= rec.weekday_morning_close:
                raise ValidationError(
                    "La apertura de mañana (L-V) debe ser anterior al cierre de mañana. "
                    "(%s ≥ %s)" % (
                        _float_to_time_str(rec.weekday_morning_open),
                        _float_to_time_str(rec.weekday_morning_close),
                    )
                )
            if rec.weekday_afternoon_open >= rec.weekday_afternoon_close:
                raise ValidationError(
                    "La apertura de tarde (L-V) debe ser anterior al cierre de tarde. "
                    "(%s ≥ %s)" % (
                        _float_to_time_str(rec.weekday_afternoon_open),
                        _float_to_time_str(rec.weekday_afternoon_close),
                    )
                )
            # El turno de mañana debe terminar ANTES de que empiece el de tarde
            if rec.weekday_morning_close > rec.weekday_afternoon_open:
                raise ValidationError(
                    "El turno de mañana (L-V) debe terminar antes de que empiece el de tarde. "
                    "Cierre mañana: %s — Apertura tarde: %s." % (
                        _float_to_time_str(rec.weekday_morning_close),
                        _float_to_time_str(rec.weekday_afternoon_open),
                    )
                )

            # ── Coherencia interna de los turnos (Sábado) ────────────────────
            if rec.saturday_active:
                if rec.saturday_morning_open >= rec.saturday_morning_close:
                    raise ValidationError(
                        "La apertura de mañana del sábado debe ser anterior al cierre. "
                        "(%s ≥ %s)" % (
                            _float_to_time_str(rec.saturday_morning_open),
                            _float_to_time_str(rec.saturday_morning_close),
                        )
                    )
                if rec.saturday_afternoon_active:
                    if rec.saturday_afternoon_open >= rec.saturday_afternoon_close:
                        raise ValidationError(
                            "La apertura de tarde del sábado debe ser anterior al cierre. "
                            "(%s ≥ %s)" % (
                                _float_to_time_str(rec.saturday_afternoon_open),
                                _float_to_time_str(rec.saturday_afternoon_close),
                            )
                        )
                    if rec.saturday_morning_close > rec.saturday_afternoon_open:
                        raise ValidationError(
                            "El turno de mañana del sábado debe terminar antes de que empiece el de tarde. "
                            "Cierre mañana: %s — Apertura tarde: %s." % (
                                _float_to_time_str(rec.saturday_morning_close),
                                _float_to_time_str(rec.saturday_afternoon_open),
                            )
                        )

    # -------------------------------------------------------------------------
    # SQL Constraints: línea de defensa extra a nivel de base de datos
    # -------------------------------------------------------------------------
    # Son más eficientes que las Python constraints para comprobaciones simples.
    # Complementan (no sustituyen) a las Python constraints anteriores.
    _check_weekday_morning_open_min = models.Constraint(
        'CHECK(weekday_morning_open >= 8)',
        'La apertura de mañana (L-V) no puede ser antes de las 08:00.',
    )
    _check_weekday_afternoon_close_max = models.Constraint(
        'CHECK(weekday_afternoon_close <= 22)',
        'El cierre de tarde (L-V) no puede ser después de las 22:00.',
    )
    _check_saturday_morning_open_min = models.Constraint(
        'CHECK(saturday_morning_open >= 8)',
        'La apertura de mañana del sábado no puede ser antes de las 08:00.',
    )
    _check_saturday_afternoon_close_max = models.Constraint(
        'CHECK(saturday_afternoon_close <= 22)',
        'El cierre de tarde del sábado no puede ser después de las 22:00.',
    )
