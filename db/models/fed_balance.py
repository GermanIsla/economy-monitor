# db/models/fed_balance.py
# Modelo para los activos del balance sheet de la Reserva Federal
# Fuente: FRED API — series semanales del H.4.1 (Assets: Securities Held Outright)

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Date, Float, String, UniqueConstraint
from db.models.base import Base, TimestampMixin
import datetime


class FedBalanceAsset(Base, TimestampMixin):
    """
    Activos en cartera de la Reserva Federal (valores en circulación).

    Tres series del H.4.1 (balance semanal, miércoles):
      - TREAST  → U.S. Treasury Securities (bonos del Tesoro)
      - FEDDT   → Federal Agency Debt Securities (deuda de agencias federales)
      - WSHOMCB → Mortgage-Backed Securities (MBS)

    Unidad: miles de millones de USD (MM USD).
    Frecuencia: semanal (miércoles).
    """
    __tablename__ = "fed_balance_assets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    series_id: Mapped[str] = mapped_column(String(20), nullable=False)   # TREAST, FEDDT, WSHOMCB
    series_name: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)           # MM USD

    __table_args__ = (
        UniqueConstraint("date", "series_id", name="uq_fed_balance_date_series"),
    )

    def __repr__(self) -> str:
        return f"<FedBalanceAsset {self.series_id} {self.date} ${self.value:.1f}B>"
