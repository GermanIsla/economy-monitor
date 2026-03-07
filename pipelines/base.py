# pipelines/base.py
# Clase abstracta que define el contrato de todos los pipelines ETL

import os
import json
from abc import ABC, abstractmethod
from datetime import datetime, date
from db.engine import get_session
from db.models.pipeline_metadata import PipelineRun
from utils.logger import get_logger
from config.settings import DATA_DIR
from sqlalchemy import select


# Directorio para datos crudos (staging)
STAGING_DIR = os.path.join(DATA_DIR, "staging")
os.makedirs(STAGING_DIR, exist_ok=True)


class BasePipeline(ABC):
    """
    Contrato que todos los pipelines deben cumplir.
    
    Soporta dos modos de descarga:
    - Incremental (por defecto): solo datos nuevos desde la última ejecución.
    - Completa (--full): todo el histórico. Para inicialización o correcciones.
    
    Cada pipeline recibe since_date en extract() y decide cómo usarlo:
    - Si la API soporta filtro por fecha: descargar solo lo nuevo.
    - Si no (ej: Excel completo de NY Fed): ignorar since_date, descargar todo,
      y dejar que el UPSERT descarte duplicados.
    """

    def __init__(self):
        self.logger = get_logger(self.name)

    @property
    @abstractmethod
    def name(self) -> str:
        """Identificador único del pipeline."""
        pass

    @abstractmethod
    def extract(self, since_date: date = None) -> any:
        """
        Descarga datos de la fuente.
        
        Args:
            since_date: Si no es None, descargar solo datos posteriores
                        a esta fecha. Si None, descargar todo.
                        Los pipelines que no soporten filtro por fecha
                        pueden ignorar este parámetro.
        """
        pass

    @abstractmethod
    def transform(self, raw_data) -> list[dict]:
        """Limpia y transforma. Valores deben ser tipos Python nativos."""
        pass

    @abstractmethod
    def load(self, clean_data: list[dict]) -> int:
        """Guarda en DB con UPSERT. Retorna nº de registros."""
        pass

    def get_last_successful_date(self) -> date | None:
        """Consulta cuándo fue la última ejecución exitosa de este pipeline."""
        try:
            with get_session() as session:
                stmt = (
                    select(PipelineRun.finished_at)
                    .where(PipelineRun.pipeline_name == self.name)
                    .where(PipelineRun.status == 'success')
                    .order_by(PipelineRun.finished_at.desc())
                    .limit(1)
                )
                result = session.execute(stmt).scalar()
                if result:
                    return result.date() if isinstance(result, datetime) else result
        except Exception:
            pass
        return None

    def _save_staging(self, raw_data) -> str:
        """Guarda datos crudos en staging tras extract()."""
        timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        filename = f"{self.name}_{timestamp}.json"
        filepath = os.path.join(STAGING_DIR, filename)

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(raw_data, f, ensure_ascii=False, default=str)
            self.logger.info(f"Datos crudos guardados en staging: {filename}")
            self._cleanup_staging()
            return filepath
        except Exception as e:
            self.logger.warning(f"No se pudo guardar staging: {e}")
            return ""

    def _cleanup_staging(self, keep: int = 5):
        """Mantiene solo los últimos N archivos de staging."""
        try:
            prefix = f"{self.name}_"
            files = sorted([
                f for f in os.listdir(STAGING_DIR)
                if f.startswith(prefix)
            ])
            for old_file in files[:-keep]:
                os.remove(os.path.join(STAGING_DIR, old_file))
                self.logger.info(f"Staging antiguo eliminado: {old_file}")
        except Exception:
            pass

    def load_from_staging(self, filepath: str = None) -> list:
        """Carga desde staging. Sin filepath, usa el más reciente."""
        if filepath is None:
            prefix = f"{self.name}_"
            files = sorted([
                f for f in os.listdir(STAGING_DIR)
                if f.startswith(prefix)
            ])
            if not files:
                raise FileNotFoundError(
                    f"No hay archivos de staging para '{self.name}'"
                )
            filepath = os.path.join(STAGING_DIR, files[-1])

        self.logger.info(f"Cargando datos desde staging: {filepath}")
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)

    def run(self, from_staging: bool = False, full: bool = False) -> bool:
        """
        Ejecuta el pipeline: Extract → Transform → Load.
        
        Args:
            from_staging: Salta extracción, usa último staging.
            full: Fuerza descarga completa ignorando modo incremental.
        """
        run_record = PipelineRun(
            pipeline_name=self.name,
            status="running",
            started_at=datetime.now()
        )

        with get_session() as session:
            session.add(run_record)
            session.commit()
            run_id = run_record.id

        try:
            # --- Extract ---
            if from_staging:
                self.logger.info("Cargando datos desde staging (sin descargar)...")
                raw_data = self.load_from_staging()
            else:
                since_date = None
                if not full:
                    since_date = self.get_last_successful_date()

                if since_date:
                    self.logger.info(f"Modo incremental: datos desde {since_date}")
                else:
                    self.logger.info("Modo completo: descargando todo el histórico")

                raw_data = self.extract(since_date=since_date)
                self._save_staging(raw_data)

            # --- Transform ---
            self.logger.info("Transformando datos...")
            clean_data = self.transform(raw_data)

            if not clean_data:
                self.logger.info("Sin datos nuevos para cargar.")
                with get_session() as session:
                    run = session.get(PipelineRun, run_id)
                    run.status = "success"
                    run.finished_at = datetime.now()
                    run.records_processed = 0
                    session.commit()
                return True

            # --- Load ---
            self.logger.info(f"Cargando {len(clean_data)} registros...")
            records = self.load(clean_data)

            with get_session() as session:
                run = session.get(PipelineRun, run_id)
                run.status = "success"
                run.finished_at = datetime.now()
                run.records_processed = records
                session.commit()

            self.logger.info(f"Completado: {records} registros procesados.")
            return True

        except Exception as e:
            self.logger.error(f"Error en el pipeline: {e}", exc_info=True)
            with get_session() as session:
                run = session.get(PipelineRun, run_id)
                run.status = "error"
                run.finished_at = datetime.now()
                run.error_message = str(e)[:500]
                session.commit()
            return False