# scheduler/jobs.py
# Registro de todos los jobs del scheduler
# Cada pipeline se registra aquí con su intervalo de ejecución

from pipelines.treasury_pipeline import TreasuryPipeline
from pipelines.nfci_pipeline import NFCIPipeline
from utils.logger import get_logger


logger = get_logger("scheduler")


def run_pipeline_safe(pipeline_class):
    """
    Wrapper que instancia y ejecuta un pipeline con manejo de errores.
    El scheduler llama a esta función, nunca directamente al pipeline.
    """
    try:
        pipeline = pipeline_class()
        pipeline.run()
    except Exception as e:
        logger.error(f"Error ejecutando {pipeline_class.__name__}: {e}")


def register_jobs(scheduler):
    """
    Registra todos los pipelines como jobs programados.
    
    Añadir nuevos jobs aquí cuando se creen nuevos pipelines.
    Usar replace_existing=True para que se actualicen al reiniciar.
    """

    # --- Tesoro USA: diariamente a las 8:00 ---
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[TreasuryPipeline],
        hour=8, minute=0,
        id='treasury_daily',
        replace_existing=True
    )

    # --- NFCI: viernes a las 12:00 (publicación semanal) ---
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[NFCIPipeline],
        day_of_week='fri', hour=12,
        id='nfci_weekly',
        replace_existing=True
    )

    # --- Repo: diariamente a las 10:00 ---
    from pipelines.repo_pipeline import RepoPipeline
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[RepoPipeline],
        hour=10, minute=0,
        id='repo_daily',
        replace_existing=True
    )

    # --- BCE: día 5 de cada mes a las 8:00 (datos MMSR son mensuales) ---
    from pipelines.ecb_pipeline import ECBPipeline
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[ECBPipeline],
        day=5, hour=8, minute=0,
        id='ecb_monthly',
        replace_existing=True
    )
    from pipelines.fed_balance_pipeline import FedBalancePipeline

    # Y en register_jobs(), añade:
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[FedBalancePipeline],
        day_of_week='thu',   # El H.4.1 se publica los jueves
        hour=20,
        id='fed_balance_weekly',
        replace_existing=True,
    )

    # --- Descomenta estos bloques cuando implementes los pipelines ---

    # from pipelines.indices_pipeline import IndicesPipeline
    # scheduler.add_job(
    #     run_pipeline_safe,
    #     trigger='interval',
    #     args=[IndicesPipeline],
    #     hours=6,
    #     id='indices_6h',
    #     replace_existing=True
    # )

    # from pipelines.repo_pipeline import RepoPipeline
    # scheduler.add_job(
    #     run_pipeline_safe,
    #     trigger='cron',
    #     args=[RepoPipeline],
    #     hour=10, minute=0,
    #     id='repo_daily',
    #     replace_existing=True
    # )

    logger.info(f"Registrados {len(scheduler.get_jobs())} jobs.")