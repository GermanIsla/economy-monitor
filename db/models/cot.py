# db/models/cot.py
# Datos COT (Commitments of Traders) de la CFTC — reporte Disaggregated Combined

from sqlalchemy import String, Integer, Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, TimestampMixin


class COTReport(Base, TimestampMixin):
    """
    Posicionamiento semanal de los grandes traders en futuros y opciones
    sobre materias primas. Fuente: CFTC Disaggregated Combined (kh3c-gbw2).

    Categorías de traders en el reporte Disaggregated:
      - Producer/Merchant: productores físicos y comerciantes. Posición estructural.
      - Swap Dealers: bancos y dealers que gestionan exposición de OTC swaps.
      - Managed Money: hedge funds y CTAs. La categoría más seguida como señal especulativa.
      - Other Reportable: otros operadores reportables que no encajan en las anteriores.
      - Non-Reportable: posiciones pequeñas por debajo del umbral de reporte.

    Columnas _all: futuros + opciones combinados (el dato más representativo del mercado total).
    Publicación: viernes ~15:30 ET con datos del martes anterior.
    Histórico disponible desde: 2006-06-13.
    """
    __tablename__ = "cot_reports"
    __table_args__ = (
        UniqueConstraint(
            'report_date', 'cftc_contract_market_code',
            name='uq_cot_report'
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- Identificación del contrato ---
    report_date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    contract_market_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    cftc_contract_market_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    commodity_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # Categoría añadida en transform(): 'energy' | 'metals' | 'grains'
    commodity_group: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # --- Interés abierto total ---
    open_interest: Mapped[int] = mapped_column(Integer, nullable=False)

    # --- Producer / Merchant (coberturistas comerciales) ---
    prod_merc_long: Mapped[int] = mapped_column(Integer, nullable=True)
    prod_merc_short: Mapped[int] = mapped_column(Integer, nullable=True)

    # --- Swap Dealers ---
    swap_long: Mapped[int] = mapped_column(Integer, nullable=True)
    swap_short: Mapped[int] = mapped_column(Integer, nullable=True)
    swap_spread: Mapped[int] = mapped_column(Integer, nullable=True)

    # --- Managed Money (fondos especulativos, hedge funds, CTAs) ---
    m_money_long: Mapped[int] = mapped_column(Integer, nullable=True)
    m_money_short: Mapped[int] = mapped_column(Integer, nullable=True)
    m_money_spread: Mapped[int] = mapped_column(Integer, nullable=True)

    # --- Other Reportable ---
    other_rept_long: Mapped[int] = mapped_column(Integer, nullable=True)
    other_rept_short: Mapped[int] = mapped_column(Integer, nullable=True)
    other_rept_spread: Mapped[int] = mapped_column(Integer, nullable=True)

    # --- Non-Reportable (pequeños especuladores) ---
    nonrept_long: Mapped[int] = mapped_column(Integer, nullable=True)
    nonrept_short: Mapped[int] = mapped_column(Integer, nullable=True)

    # --- Cambios semanales (respecto al reporte anterior) ---
    change_open_interest: Mapped[int] = mapped_column(Integer, nullable=True)
    change_prod_merc_long: Mapped[int] = mapped_column(Integer, nullable=True)
    change_prod_merc_short: Mapped[int] = mapped_column(Integer, nullable=True)
    change_swap_long: Mapped[int] = mapped_column(Integer, nullable=True)
    change_swap_short: Mapped[int] = mapped_column(Integer, nullable=True)
    change_m_money_long: Mapped[int] = mapped_column(Integer, nullable=True)
    change_m_money_short: Mapped[int] = mapped_column(Integer, nullable=True)