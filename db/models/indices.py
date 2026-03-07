# db/models/indices.py
# Modelos de datos para índices de mercado y ETFs
# Fuente: Yahoo Finance u otras APIs de mercado

from sqlalchemy import String, Float, Date, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, TimestampMixin


class MarketIndex(Base, TimestampMixin):
    """Datos diarios de índices de mercado (SP500, NASDAQ, DAX, etc.)."""
    __tablename__ = "market_indices"
    __table_args__ = (
        UniqueConstraint('date', 'index_symbol', name='uq_market_index'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    index_symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    index_name: Mapped[str] = mapped_column(String(100), nullable=False)
    close_price: Mapped[float] = mapped_column(Float, nullable=False)
    open_price: Mapped[float] = mapped_column(Float, nullable=True)
    high_price: Mapped[float] = mapped_column(Float, nullable=True)
    low_price: Mapped[float] = mapped_column(Float, nullable=True)
    volume: Mapped[float] = mapped_column(Float, nullable=True)


class ETFPrice(Base, TimestampMixin):
    """Precios diarios de ETFs para comparativas de fuerza relativa."""
    __tablename__ = "etf_prices"
    __table_args__ = (
        UniqueConstraint('date', 'ticker', name='uq_etf_price'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    close_price: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=True)
