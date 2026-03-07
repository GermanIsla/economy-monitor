# db/models/gcf_repo.py
# Modelos de datos adicionales del mercado de Repo
# Datos de las hojas gcf_repo_total, triparty_gcf, gcf_repo_asset_classes y gcf_repo_gcf_cusips

from sqlalchemy import String, Float, Date, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, TimestampMixin


class GCFRepoTotal(Base, TimestampMixin):
    """
    Totales mensuales del mercado GCF Repo.
    Métricas: Gross Securities, Net Cash Borrowed, Net Securities Delivered.
    Fuente: hoja 'gcf_repo_total' del Excel de la NY Fed.
    """
    __tablename__ = "gcf_repo_total"
    __table_args__ = (
        UniqueConstraint('date', 'metric_type', name='uq_gcf_repo_total'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    metric_type: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)


class RepoMarketSplit(Base, TimestampMixin):
    """
    Desglose del volumen entre mercado Tri-Party puro y GCF Repo,
    por tipo de colateral (Treasury, Agency MBS, Agency other).
    Fuente: hoja 'triparty_gcf' del Excel de la NY Fed.
    """
    __tablename__ = "repo_market_split"
    __table_args__ = (
        UniqueConstraint('date', 'collateral_type', name='uq_repo_market_split'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    collateral_type: Mapped[str] = mapped_column(String(100), nullable=False)
    tpr_value: Mapped[float] = mapped_column(Float, nullable=True)
    tpr_share: Mapped[float] = mapped_column(Float, nullable=True)
    gcf_value: Mapped[float] = mapped_column(Float, nullable=True)
    gcf_share: Mapped[float] = mapped_column(Float, nullable=True)


class GCFRepoAssetClass(Base, TimestampMixin):
    """
    Desglose del GCF Repo por clase de activo, separando overnight y a plazo (term).
    Fuente: hoja 'gcf_repo_asset_classes' del Excel de la NY Fed.
    """
    __tablename__ = "gcf_repo_asset_classes"
    __table_args__ = (
        UniqueConstraint('date', 'collateral_type', name='uq_gcf_asset_class'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    collateral_type: Mapped[str] = mapped_column(String(100), nullable=False)
    overnight: Mapped[float] = mapped_column(Float, nullable=True)
    overnight_share: Mapped[float] = mapped_column(Float, nullable=True)
    term: Mapped[float] = mapped_column(Float, nullable=True)
    term_share: Mapped[float] = mapped_column(Float, nullable=True)


class GCFRepoCUSIP(Base, TimestampMixin):
    """
    Desglose granular del GCF Repo por tipo de CUSIP, separando overnight y term.
    Incluye: GNMA, FNMA, FHLMC, TIPs, STRIPs, Treasury por plazo, etc.
    Fuente: hoja 'gcf_repo_gcf_cusips' del Excel de la NY Fed.
    """
    __tablename__ = "gcf_repo_cusips"
    __table_args__ = (
        UniqueConstraint('date', 'collateral_type', name='uq_gcf_cusip'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    collateral_type: Mapped[str] = mapped_column(String(150), nullable=False)
    overnight: Mapped[float] = mapped_column(Float, nullable=True)
    overnight_share: Mapped[float] = mapped_column(Float, nullable=True)
    term: Mapped[float] = mapped_column(Float, nullable=True)
    term_share: Mapped[float] = mapped_column(Float, nullable=True)
