# db/models/commodity_price.py
# Precios históricos de materias primas. Fuente: Alpha Vantage.

from sqlalchemy import String, Float, Date, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, TimestampMixin


class CommodityPrice(Base, TimestampMixin):
    """
    Precio semanal o mensual de una materia prima.
    Fuente: Alpha Vantage Commodities API + FX API (oro/plata).

    series_id corresponde a la función de Alpha Vantage:
      'WTI'          → Crudo WTI (USD/barril, semanal)
      'NATURAL_GAS'  → Gas natural Henry Hub (USD/MMBtu, semanal)
      'GOLD'         → Oro spot XAU/USD (USD/oz troy, semanal)
      'SILVER'       → Plata spot XAG/USD (USD/oz troy, semanal)
      'COPPER'       → Cobre (USD/lb, mensual → interpolado a semanal)
      'WHEAT'        → Trigo (USD/bushel, mensual → interpolado)
      'CORN'         → Maíz (USD/bushel, mensual → interpolado)
    """
    __tablename__ = "commodity_prices"
    __table_args__ = (
        UniqueConstraint('date', 'series_id', name='uq_commodity_price'),
    )

    id:        Mapped[int]   = mapped_column(Integer, primary_key=True, autoincrement=True)
    date:      Mapped[Date]  = mapped_column(Date,        nullable=False, index=True)
    series_id: Mapped[str]   = mapped_column(String(30),  nullable=False, index=True)
    price:     Mapped[float] = mapped_column(Float,       nullable=False)
    unit:      Mapped[str]   = mapped_column(String(50),  nullable=True)