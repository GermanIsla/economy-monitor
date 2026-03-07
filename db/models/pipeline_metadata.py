# db/models/pipeline_metadata.py
# Registro de ejecuciones de pipelines (estado, errores, tiempos)

from sqlalchemy import String, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class PipelineRun(Base):
    """
    Registro de cada ejecución de un pipeline.
    El dashboard consulta esta tabla para mostrar el estado del sistema.
    
    Estados posibles:
    - 'running': Pipeline en ejecución
    - 'success': Completado correctamente
    - 'error': Falló durante la ejecución
    """
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[DateTime] = mapped_column(DateTime, nullable=True)
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
