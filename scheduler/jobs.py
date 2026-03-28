# scheduler/jobs.py
# Registro de todos los jobs del scheduler

from datetime import datetime, timedelta

from pipelines.treasury_pipeline import TreasuryPipeline
from pipelines.nfci_pipeline import NFCIPipeline
from pipelines.repo_pipeline import RepoPipeline
from pipelines.ecb_pipeline import ECBPipeline
from pipelines.fed_balance_pipeline import FedBalancePipeline
from pipelines.cot_pipeline import COTPipeline
from pipelines.commodity_price_pipeline import CommodityPricePipeline
from utils.logger import get_logger

logger = get_logger("scheduler")

# Orden en que se comprueban/ejecutan los pipelines en el catch-up de arranque.
# Los más críticos o ligeros van primero.
ALL_PIPELINES = [
    TreasuryPipeline,
    NFCIPipeline,
    RepoPipeline,
    ECBPipeline,
    FedBalancePipeline,
    COTPipeline,
    CommodityPricePipeline,
]


def run_pipeline_safe(pipeline_class):
    """
    Wrapper que instancia y ejecuta un pipeline con manejo de errores.
    Comprueba frescura antes de ejecutar: si los datos están vigentes, omite la descarga.
    """
    try:
        pipeline = pipeline_class()
        if pipeline.is_fresh():
            logger.info(f"[{pipeline.name}] Datos vigentes (dentro de {pipeline.min_interval_hours:.0f}h). Omitiendo ejecución.")
            return
        logger.info(f"[{pipeline.name}] Iniciando descarga...")
        pipeline.run()
    except Exception as e:
        logger.error(f"Error ejecutando {pipeline_class.__name__}: {e}")


def schedule_startup_catchup(scheduler):
    """
    Al arrancar la aplicación, comprueba qué pipelines tienen datos desactualizados
    y programa ejecuciones one-shot escalonadas para ponerlos al día.

    Los pipelines se ejecutan de uno en uno con un margen de tiempo entre ellos
    para no saturar las APIs ni la base de datos.
    """
    FIRST_DELAY_MINUTES = 2   # El primer pipeline desactualizado arranca a los 2 min
    STEP_MINUTES = 8          # Cada pipeline adicional espera 8 min más

    scheduled = 0
    for pipeline_class in ALL_PIPELINES:
        try:
            pipeline = pipeline_class()
            if not pipeline.is_fresh():
                run_at = datetime.now() + timedelta(
                    minutes=FIRST_DELAY_MINUTES + scheduled * STEP_MINUTES
                )
                scheduler.add_job(
                    run_pipeline_safe,
                    trigger='date',
                    run_date=run_at,
                    args=[pipeline_class],
                    id=f'catchup_{pipeline.name}',
                    replace_existing=True
                )
                logger.info(
                    f"[{pipeline.name}] Desactualizado. Catch-up programado a las {run_at.strftime('%H:%M:%S')}"
                )
                scheduled += 1
            else:
                logger.info(f"[{pipeline.name}] Al día. No necesita catch-up.")
        except Exception as e:
            logger.warning(f"Error comprobando {pipeline_class.__name__}: {e}")

    if scheduled == 0:
        logger.info("Todos los pipelines están al día. No se necesita catch-up.")
    else:
        total_minutes = FIRST_DELAY_MINUTES + (scheduled - 1) * STEP_MINUTES
        logger.info(
            f"{scheduled} pipeline(s) desactualizados. "
            f"Catch-up escalonado completado en ~{total_minutes} min."
        )


def register_jobs(scheduler):
    """
    Registra todos los pipelines como jobs cron recurrentes.
    Añadir nuevos jobs aquí cuando se creen nuevos pipelines.
    """

    # Treasury: diariamente a las 8:00
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[TreasuryPipeline],
        hour=8, minute=0,
        id='treasury_daily',
        replace_existing=True
    )

    # NFCI: viernes a las 12:00 (publicación semanal)
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[NFCIPipeline],
        day_of_week='fri', hour=12, minute=0,
        id='nfci_weekly',
        replace_existing=True
    )

    # Repo: diariamente a las 10:00
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[RepoPipeline],
        hour=10, minute=0,
        id='repo_daily',
        replace_existing=True
    )

    # BCE: día 5 de cada mes a las 8:00 (datos MMSR son mensuales)
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[ECBPipeline],
        day=5, hour=8, minute=0,
        id='ecb_monthly',
        replace_existing=True
    )

    # Fed Balance: jueves a las 20:00 (H.4.1 se publica ~17:00-18:00 ET)
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[FedBalancePipeline],
        day_of_week='thu', hour=20, minute=0,
        id='fed_balance_weekly',
        replace_existing=True
    )

    # COT: viernes a las 22:00 (~15:30 ET = ~21:30 Madrid)
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[COTPipeline],
        day_of_week='fri', hour=22, minute=0,
        id='cot_weekly',
        replace_existing=True
    )

    # Precios commodities: lunes a las 8:30
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[CommodityPricePipeline],
        day_of_week='mon', hour=8, minute=30,
        id='commodity_prices_weekly',
        replace_existing=True
    )

    logger.info(f"Registrados {len(scheduler.get_jobs())} jobs.")
