#!/usr/bin/env python3
# run_app.py
# Punto de entrada unificado para despliegue web.
# Arranca el scheduler en background y el dashboard en el mismo proceso.
#
# Uso:
#   python run_app.py
#
# El scheduler comprueba al arrancar qué pipelines están desactualizados
# y los ejecuta de forma escalonada. A partir de ahí, los cron jobs
# se encargan de mantener los datos al día automáticamente.

import sys
from db.engine import init_db
from config.settings import DASH_HOST, DASH_PORT

def main():
    print("Inicializando base de datos...")
    init_db()

    # Arrancar scheduler en background antes del dashboard
    from scheduler.runner import create_scheduler
    from scheduler.jobs import register_jobs, schedule_startup_catchup

    scheduler = create_scheduler()
    register_jobs(scheduler)
    scheduler.start()

    print("Scheduler arrancado. Comprobando pipelines desactualizados...")
    schedule_startup_catchup(scheduler)

    # Importar la app después de init_db para garantizar tablas creadas
    from dashboard.app import app

    print(f"\n{'='*50}")
    print(f"  Economy Monitor — Modo Web")
    print(f"  http://{DASH_HOST}:{DASH_PORT}")
    print(f"{'='*50}\n")

    # debug=False es obligatorio en producción:
    # el modo debug arranca Flask dos veces (reloader), lo que duplicaría el scheduler.
    try:
        app.run(host=DASH_HOST, port=DASH_PORT, debug=False)
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
