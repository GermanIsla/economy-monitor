# scheduler/runner.py
# Creación y configuración del scheduler APScheduler

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from config.settings import DB_PATH


def create_scheduler() -> BackgroundScheduler:
    """
    Crea el scheduler con persistencia en SQLite.
    
    Configuración:
    - coalesce: Si se acumulan ejecuciones perdidas, solo ejecutar una
    - max_instances: No ejecutar el mismo job en paralelo
    - misfire_grace_time: Tolerancia de 1h si se pierde la ventana de ejecución
    """
    scheduler = BackgroundScheduler(
        jobstores={
            'default': SQLAlchemyJobStore(url=f'sqlite:///{DB_PATH}')
        },
        job_defaults={
            'coalesce': True,
            'max_instances': 1,
            'misfire_grace_time': 3600,
        }
    )
    return scheduler
