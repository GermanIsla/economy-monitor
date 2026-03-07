# db/models/__init__.py
# Importar TODOS los modelos aquí para que Alembic los detecte automáticamente.
# Cada vez que se cree un nuevo modelo, añadir su import aquí.

from .base import Base, TimestampMixin
from .pipeline_metadata import PipelineRun
from .treasury import TreasuryAuction
from .nfci import NFCIReading
from .indices import MarketIndex, ETFPrice
from .repo import RepoOperation
from .gcf_repo import GCFRepoTotal, RepoMarketSplit, GCFRepoAssetClass, GCFRepoCUSIP
from .ecb import ECBRate, ECBBalanceSheet

__all__ = [
    'Base', 'TimestampMixin', 'PipelineRun',
    'TreasuryAuction', 'NFCIReading',
    'MarketIndex', 'ETFPrice',
    'RepoOperation',
    'GCFRepoTotal', 'RepoMarketSplit', 'GCFRepoAssetClass', 'GCFRepoCUSIP',
    'ECBRate', 'ECBBalanceSheet',
]