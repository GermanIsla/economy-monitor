# db/models/nfci.py
# Modelo de datos para el indicador NFCI (National Financial Conditions Index)
# Fuente: FRED API (Fed de Chicago, publicación semanal)

from sqlalchemy import String, Float, Date, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, TimestampMixin


class NFCIReading(Base, TimestampMixin):
    """
    Lectura semanal del indicador NFCI de la Fed de Chicago.
    Valores positivos indican condiciones financieras más restrictivas.
    Valores negativos indican condiciones más laxas.
    """
    __tablename__ = "nfci_readings"
    __table_args__ = (
        UniqueConstraint('date', 'indicator_name', name='uq_nfci_reading'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    indicator_name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
