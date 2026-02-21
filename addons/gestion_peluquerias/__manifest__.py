# -*- coding: utf-8 -*-
{
    'name': 'StyleHub - Gestión de Peluquería',
    'version': '19.0.1.0.0',
    'summary': 'Gestión de citas, servicios y estilistas para peluquerías',
    'description': """
StyleHub - Gestión de Peluquería
=================================

Módulo completo para la gestión de una peluquería profesional.

Funcionalidades
---------------
- Catálogo de servicios con precio y duración
- Gestión de estilistas (empleados)
- Gestión de citas con múltiples servicios por cita
- Cálculo automático de hora de fin según servicios
- Validación de solapamiento de citas por estilista
- Flujo de estados: Borrador → Confirmada → Realizada / Cancelada
- Vista calendario con bloques de duración real
- Vista Kanban agrupada por estado
- Detección automática de clientes frecuentes (VIP)
""",
    'author': 'Alex Martinez Juan',
    'website': '',
    'category': 'Services',
    'application': True,
    'installable': True,
    'depends': ['base', 'contacts'],
    'data': [
        'security/ir.model.access.csv',
        'views/stylehub_service_views.xml',
        'views/stylehub_stylist_views.xml',
        'views/stylehub_appointment_views.xml',
        'views/stylehub_appointment_kanban_views.xml',
        'views/res_partner_views.xml',
        'views/stylehub_menus.xml',
    ],
}
