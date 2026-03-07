# db/models/ecb.py
# Modelos de datos del Banco Central Europeo
# Fuente: API del BCE + web scraping

from sqlalchemy import String, Float, Date, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, TimestampMixin


class ECBRate(Base, TimestampMixin):
    """Tipos de interés oficiales del Banco Central Europeo."""
    __tablename__ = "ecb_rates"
    __table_args__ = (
        UniqueConstraint('date', 'rate_type', name='uq_ecb_rate'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    rate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)


class ECBBalanceSheet(Base, TimestampMixin):
    """Partidas del balance del BCE (activos totales, préstamos, etc.)."""
    __tablename__ = "ecb_balance_sheet"
    __table_args__ = (
        UniqueConstraint('date', 'item_name', name='uq_ecb_balance'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=True)
