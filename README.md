# StyleHub — Módulo de Gestión de Peluquería para Odoo 19

Módulo personalizado de Odoo 19 desarrollado para **StyleHub**, una peluquería profesional que necesita digitalizar su agenda, catálogo de servicios y gestión de clientes.

---

## Índice

1. [Requisitos previos](#requisitos-previos)
2. [⚠️ Configuración obligatoria tras la instalación](#️-configuración-obligatoria-tras-la-instalación)
3. [Instalación y arranque](#instalación-y-arranque)
4. [Estructura del proyecto](#estructura-del-proyecto)
5. [Modelos del módulo](#modelos-del-módulo)
6. [Funcionalidades principales](#funcionalidades-principales)
7. [Flujo de trabajo de una cita](#flujo-de-trabajo-de-una-cita)
8. [Vistas disponibles](#vistas-disponibles)
9. [Validaciones y restricciones](#validaciones-y-restricciones)
10. [Clientes VIP](#clientes-vip)
11. [Variables de entorno](#variables-de-entorno)

---

## Requisitos previos

- [Docker](https://www.docker.com/) y Docker Compose instalados
- Puerto **8069** libre (Odoo)
- Puerto **5432** libre (PostgreSQL)
- Puerto **5050** libre (pgAdmin)

---

## ⚠️ Configuración obligatoria tras la instalación

> **IMPORTANTE:** Sin este paso, las validaciones de horario y fechas no funcionarán correctamente, ya que Odoo almacena todas las fechas en UTC internamente y necesita saber tu zona horaria real para convertirlas.

Nada más entrar a Odoo por primera vez, configura la zona horaria del usuario:

```
Ajustes → Usuarios y Compañías → Usuarios → [Seleccionar tu usuario] → Pestaña "Preferencias" → Zona Horaria → Europe/Madrid
```

Sin esta configuración, las horas mostradas en el calendario y los mensajes de error de validación de horario comercial mostrarán la hora en UTC (1-2 horas menos que la hora real peninsular española).

---

## Instalación y arranque

### 1. Clonar el repositorio

```bash
git clone <url-del-repositorio>
cd odoo_stylehub
```

### 2. Crear el archivo `.env`

Copia el ejemplo y ajusta los valores si es necesario:

```bash
cp .env.example .env   # si existe, o créalo manualmente
```

Contenido del `.env`:

```env
ODOO_PORT=8069
DB_HOST=db
DB_USER=odoo
DB_PASSWORD=odoo
PGADMIN_EMAIL=admin@admin.com
PGADMIN_PASSWORD=admin
PGADMIN_PORT=5050
```

### 3. Crear el archivo `config/odoo.conf`

Copia el ejemplo incluido en el repositorio:

```bash
cp config/odoo.conf.example config/odoo.conf
```

> `config/odoo.conf` está en `.gitignore` y no se sube al repositorio por seguridad.

### 4. Arrancar los contenedores

```bash
docker compose up -d
```

### 5. Acceder a Odoo

| Servicio | URL | Credenciales por defecto |
|---|---|---|
| Odoo | http://localhost:8069 | admin / admin |
| pgAdmin | http://localhost:5050 | admin@admin.com / admin |

### 6. Instalar el módulo

1. Ir a **Aplicaciones**
2. Hacer clic en **Actualizar lista de aplicaciones**
3. Buscar `StyleHub` o `gestion_peluquerias`
4. Hacer clic en **Instalar**

### 7. Detener los contenedores

```bash
docker compose stop
```

Para eliminar también los volúmenes de datos (⚠️ borra la base de datos):

```bash
docker compose down -v
```

---

## Estructura del proyecto

```
odoo_stylehub/
├── addons/
│   └── gestion_peluquerias/
│       ├── __init__.py
│       ├── __manifest__.py
│       ├── models/
│       │   ├── __init__.py
│       │   ├── stylehub_service.py       # Catálogo de servicios
│       │   ├── stylehub_stylist.py       # Estilistas / empleados
│       │   ├── stylehub_schedule.py      # Horario comercial (singleton)
│       │   ├── stylehub_appointment.py   # Citas y líneas de servicio
│       │   └── res_partner.py            # Extensión del cliente de Odoo
│       ├── security/
│       │   └── ir.model.access.csv       # Permisos de acceso
│       └── views/
│           ├── stylehub_service_views.xml
│           ├── stylehub_stylist_views.xml
│           ├── stylehub_schedule_views.xml
│           ├── stylehub_appointment_views.xml
│           ├── stylehub_appointment_kanban_views.xml
│           ├── res_partner_views.xml
│           └── stylehub_menus.xml
├── config/
│   ├── odoo.conf             # Configuración real (NO se sube a Git)
│   └── odoo.conf.example     # Plantilla de configuración
├── docker-compose.yml
├── .env                      # Variables de entorno (NO se sube a Git)
└── .gitignore
```

---

## Modelos del módulo

### `stylehub.service` — Catálogo de Servicios

Almacena los servicios que ofrece la peluquería.

| Campo | Tipo | Descripción |
|---|---|---|
| `name` | Char | Nombre del servicio (único, obligatorio) |
| `description` | Text | Descripción del servicio |
| `price` | Float | Precio base en euros (≥ 0) |
| `duration` | Float | Duración en horas decimales (> 0). Ej: `0.5` = 30 min, `1.5` = 1h 30min |
| `active` | Boolean | Permite archivar servicios sin borrarlos |
| `image_1920` | Binary | Foto del servicio (vía `image.mixin`) |

### `stylehub.stylist` — Estilistas

Representa a cada empleado/a de la peluquería.

| Campo | Tipo | Descripción |
|---|---|---|
| `name` | Char | Nombre (único, obligatorio) |
| `active` | Boolean | `False` = archivado (no aparece en nuevas citas) |
| `phone` | Char | Teléfono de contacto |
| `email` | Char | Correo electrónico |
| `appointment_ids` | One2many | Todas las citas asignadas al estilista |
| `image_1920` | Binary | Foto del estilista (vía `image.mixin`) |

### `stylehub.schedule` — Horario Comercial (Singleton)

Configuración única del horario de apertura de la peluquería. Solo puede existir un registro.

| Turno | Campos |
|---|---|
| Lunes a Viernes — Mañana | `weekday_morning_open`, `weekday_morning_close` |
| Lunes a Viernes — Tarde | `weekday_afternoon_open`, `weekday_afternoon_close` |
| Sábado — Mañana (opcional) | `saturday_active`, `saturday_morning_open`, `saturday_morning_close` |
| Sábado — Tarde (opcional) | `saturday_afternoon_active`, `saturday_afternoon_open`, `saturday_afternoon_close` |
| Domingo | Siempre cerrado (no configurable) |

Los horarios se introducen en **formato decimal**: `9.5` = 09:30, `13.5` = 13:30, `20.0` = 20:00.

> El horario no puede modificarse si existen citas en estado **Borrador** o **Confirmada**.

### `stylehub.appointment` — Citas

Núcleo del módulo. Cada cita pertenece a un cliente y un estilista.

| Campo | Tipo | Descripción |
|---|---|---|
| `name` | Char | Referencia generada automáticamente |
| `partner_id` | Many2one | Cliente (`res.partner`) |
| `stylist_id` | Many2one | Estilista asignado |
| `date_start` | Datetime | Fecha y hora de inicio |
| `date_end` | Datetime | **Calculado automáticamente** sumando las duraciones de los servicios |
| `line_ids` | One2many | Servicios incluidos en la cita |
| `total_duration` | Float | Suma de duraciones de los servicios (horas) |
| `total_amount` | Float | Suma de precios de los servicios (€) |
| `discount_amount` | Float | Descuento VIP del 5% si aplica (€) |
| `final_amount` | Float | Total a pagar tras descuento (€) |
| `state` | Selection | Estado: `draft`, `confirmed`, `done`, `cancelled` |
| `notes` | Text | Notas internas |

### `stylehub.appointment.line` — Líneas de Servicio

Cada registro es un servicio dentro de una cita.

| Campo | Tipo | Descripción |
|---|---|---|
| `appointment_id` | Many2one | Cita a la que pertenece |
| `service_id` | Many2one | Servicio seleccionado |
| `price_unit` | Float | Precio (se rellena automáticamente, editable) |
| `duration` | Float | Duración en horas (se rellena automáticamente, editable) |

### `res.partner` (extensión) — Clientes

Extensión del modelo de clientes de Odoo con campos específicos de StyleHub.

| Campo | Tipo | Descripción |
|---|---|---|
| `appointment_ids` | One2many | Todas las citas del cliente |
| `appointment_done_count` | Integer | Número de citas realizadas |
| `is_frequent_client` | Boolean | `True` si tiene más de 5 citas realizadas (VIP) |

---

## Funcionalidades principales

### Cálculo automático de hora de fin

Al añadir servicios a una cita, el sistema suma sus duraciones y calcula automáticamente la `date_end`. Si la cita empieza a las 10:00 y se añaden un Corte (0.5h) y un Tinte (2h), la cita termina automáticamente a las **12:30**.

### Precio automático editable

Al seleccionar un servicio en una línea, el precio base se rellena automáticamente desde el catálogo. El recepcionista puede modificarlo manualmente (por ejemplo, para aplicar un recargo).

### Validación anti-solape

El sistema impide guardar una cita si el estilista seleccionado ya tiene otra cita que se solapa en ese mismo rango de tiempo. Se muestra un error con el intervalo conflictivo.

### Validación de horario comercial

Las citas solo pueden crearse dentro del horario configurado en **StyleHub → Configuración → Horario**. Si la cita cae en domingo, fuera del horario, o en el descanso de mediodía, el sistema lo rechaza con un mensaje descriptivo.

---

## Flujo de trabajo de una cita

```
Borrador (draft)
    │
    │  [Botón: Confirmar Cita]
    ▼
Confirmada (confirmed)
    │
    ├──[Botón: Finalizar Trabajo]──▶ Realizada (done)
    │
    └──[Botón: Cancelar]──────────▶ Cancelada (cancelled)
```

- Desde **Borrador** también se puede cancelar directamente.
- Una cita **Realizada** o **Cancelada** no puede cambiar de estado.
- Los campos de cliente, estilista, fecha y servicios solo son editables en estado **Borrador**.

---

## Vistas disponibles

### Citas (`StyleHub → Agenda → Citas`)

| Vista | Descripción |
|---|---|
| **Lista** | Tabla con colores según estado (verde = confirmada, negrita = realizada, gris = cancelada) |
| **Formulario** | Detalle completo con líneas de servicio, totales y barra de estado |
| **Calendario** | Vista semanal con bloques de duración real, coloreados por estilista |
| **Kanban** | Tablero agrupado por estado con insignia VIP |

### Servicios (`StyleHub → Configuración → Servicios`)

Lista y formulario para gestionar el catálogo de servicios con precio, duración e imagen.

### Estilistas (`StyleHub → Configuración → Estilistas`)

Lista y formulario con foto, datos de contacto y listado de citas asignadas.

### Horario (`StyleHub → Configuración → Horario`)

Formulario único (singleton) para configurar los turnos de apertura y cierre de la peluquería.

### Ficha del Cliente (`Contactos → [cualquier cliente]`)

La ficha estándar de Odoo muestra una pestaña **"Citas en StyleHub"** con el historial de citas y la insignia **⭐ Cliente VIP** si procede.

---

## Validaciones y restricciones

### SQL Constraints (base de datos)

| Modelo | Restricción |
|---|---|
| `stylehub.service` | Precio ≥ 0, duración > 0, nombre único |
| `stylehub.stylist` | Nombre único |
| `stylehub.appointment.line` | Precio ≥ 0, duración > 0 |
| `stylehub.schedule` | Apertura mínima 08:00, cierre máximo 22:00 |

### Python Constraints (servidor)

| Validación | Descripción |
|---|---|
| Anti-solape | Un estilista no puede tener dos citas en el mismo horario |
| Horario comercial | Las citas deben estar dentro del horario configurado |
| No citas en el pasado | No se pueden crear citas con fecha pasada (en estado Borrador o Confirmada) |
| Al menos un servicio | Una cita debe tener como mínimo una línea de servicio |
| Coherencia de horarios | En el horario, la apertura debe ser anterior al cierre en cada turno |

### Protecciones adicionales

- **Archivar un estilista** con citas activas está bloqueado hasta cancelar o reasignarlas.
- **Archivar un servicio** en uso en citas activas está bloqueado.
- **Archivar un cliente** con citas activas está bloqueado.
- **Eliminar el horario** no está permitido.
- **Modificar el horario** con citas activas no está permitido.

---

## Clientes VIP

Un cliente se marca automáticamente como **Cliente Frecuente (VIP)** cuando supera las **5 citas en estado "Realizada"**.

Efectos:
- Aparece una insignia **⭐ Cliente VIP** en su ficha de contacto.
- En el formulario de la cita se muestra el aviso **⭐ VIP — Descuento 5%**.
- Se aplica automáticamente un **descuento del 5%** sobre el subtotal de la cita, visible en la vista Kanban y en el formulario.
- La insignia VIP también aparece en la tarjeta Kanban de cada cita.

---

## Variables de entorno

El archivo `.env` (no incluido en Git) controla la configuración del entorno:

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `ODOO_PORT` | Puerto externo de Odoo | `8069` |
| `DB_HOST` | Host de PostgreSQL | `db` |
| `DB_USER` | Usuario de la base de datos | `odoo` |
| `DB_PASSWORD` | Contraseña de la base de datos | `odoo` |
| `PGADMIN_EMAIL` | Email de acceso a pgAdmin | `admin@admin.com` |
| `PGADMIN_PASSWORD` | Contraseña de pgAdmin | `admin` |
| `PGADMIN_PORT` | Puerto externo de pgAdmin | `5050` |

---

## Autor

**Alex Martinez Juan** — 2º DAM · Módulo SGE  
