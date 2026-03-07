#!/usr/bin/env python3
# run_scheduler.py
# Punto de entrada: arranca las descargas automáticas en background

import time
from db.engine import init_db
from scheduler.runner import create_scheduler
from scheduler.jobs import register_jobs
from utils.logger import get_logger

logger = get_logger("main")

if __name__ == "__main__":
    # Asegurar que la base de datos y tablas existen
    print("Inicializando base de datos...")
    init_db()

    # Crear y arrancar scheduler
    scheduler = create_scheduler()
    register_jobs(scheduler)
    scheduler.start()

    print(f"\n{'='*50}")
    print(f"  Economy Monitor Scheduler")
    print(f"  Descargas automáticas activadas")
    print(f"  Ctrl+C para detener")
    print(f"{'='*50}\n")

    logger.info("Scheduler arrancado.")

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        scheduler.shutdown()
        logger.info("Scheduler detenido.")
        print("\nScheduler detenido correctamente.")
