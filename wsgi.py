#!/usr/bin/env python3
# wsgi.py
# Punto de entrada para PythonAnywhere (y cualquier servidor WSGI).
# PythonAnywhere busca el objeto `application` en este fichero.

import sys
import os

# Asegurar que el directorio del proyecto está en el path.
# Ajusta esta ruta al directorio real en PythonAnywhere.
project_home = os.path.dirname(os.path.abspath(__file__))
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Cargar variables de entorno desde .env (API keys, etc.)
from dotenv import load_dotenv
load_dotenv(os.path.join(project_home, '.env'))

# Inicializar base de datos (crea tablas si no existen)
from db.engine import init_db
init_db()

# Arrancar scheduler en background
from scheduler.runner import create_scheduler
from scheduler.jobs import register_jobs, schedule_startup_catchup

scheduler = create_scheduler()
register_jobs(scheduler)
scheduler.start()
schedule_startup_catchup(scheduler)

# Importar la app Dash — exponer el servidor Flask subyacente como `application`
from dashboard.app import app
application = app.server
