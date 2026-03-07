# db/models/repo.py
# Modelo de datos para operaciones de Repo Tri-Party
# Fuente: Federal Reserve Bank of New York
# https://www.newyorkfed.org/data-and-statistics/data-visualization/tri-party-repo

from sqlalchemy import String, Float, Date, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, TimestampMixin


class RepoOperation(Base, TimestampMixin):
    """
    Registro diario del mercado de Repo Tri-Party por tipo de colateral.
    Cada fila representa un grupo de colateral en una fecha concreta.
    
    Campos del Excel original:
    - date: Fecha del registro
    - group_id: ID numérico del grupo de colateral
    - group_name: Nombre descriptivo (ej: 'Equities', 'US Treasuries excluding Strips')
    - collateral_value: Volumen en miles de millones de USD
    - share_of_total: Porcentaje del total
    - top_3_concentration: Concentración de los 3 mayores participantes
    - margin_p10/median/p90: Percentiles de margen (haircut)
    - fedwire_eligible: Elegibilidad Fedwire
    - num_observations: Número de observaciones
    - margin_stdev: Desviación estándar del margen
    """
    __tablename__ = "repo_operations"
    __table_args__ = (
        UniqueConstraint(
            'date', 'group_name',
            name='uq_repo_operation'
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    group_id: Mapped[int] = mapped_column(Integer, nullable=True)
    group_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    collateral_value: Mapped[float] = mapped_column(Float, nullable=False)
    share_of_total: Mapped[float] = mapped_column(Float, nullable=True)
    top_3_concentration: Mapped[float] = mapped_column(Float, nullable=True)
    margin_p10: Mapped[float] = mapped_column(Float, nullable=True)
    margin_median: Mapped[float] = mapped_column(Float, nullable=True)
    margin_p90: Mapped[float] = mapped_column(Float, nullable=True)
    fedwire_eligible: Mapped[float] = mapped_column(Float, nullable=True)
    num_observations: Mapped[int] = mapped_column(Integer, nullable=True)
    margin_stdev: Mapped[float] = mapped_column(Float, nullable=True)