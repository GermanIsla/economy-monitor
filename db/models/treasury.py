# db/models/treasury.py
# Modelo de datos para subastas del Tesoro de EE.UU.
# Fuente: FiscalData API (api.fiscaldata.treasury.gov)

from sqlalchemy import String, Float, Date, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, TimestampMixin


class TreasuryAuction(Base, TimestampMixin):
    """
    Registro de cada subasta del Tesoro de EE.UU.
    Incluye Bills (letras), Notes (bonos a medio plazo) y Bonds (bonos a largo plazo).
    """
    __tablename__ = "treasury_auctions"
    __table_args__ = (
        UniqueConstraint(
            'issue_date', 'security_type', 'maturity_date',
            name='uq_treasury_auction'
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    maturity_date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    security_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    security_term: Mapped[str] = mapped_column(String(50), nullable=True)
    total_accepted: Mapped[float] = mapped_column(Float, nullable=False)
