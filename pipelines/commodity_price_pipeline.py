# pipelines/commodity_price_pipeline.py
# Descarga precios históricos de materias primas desde Alpha Vantage.

import os
from datetime import date, datetime

import pandas as pd
import requests
from dotenv import load_dotenv
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert

from config.settings import SOURCES
from db.engine import get_session
from db.models.commodity_price import CommodityPrice
from pipelines.base import BasePipeline
from utils.rate_limiter import RateLimiter

# ---------------------------------------------------------------------------
# Series a descargar y su mapeo en Alpha Vantage
#
# Formato: series_id → (tipo, params_extra, unit)
#   tipo 'commodity' → endpoint /query?function=WTI&interval=weekly
#   tipo 'fx'        → endpoint /query?function=FX_WEEKLY&from_symbol=XAU&to_symbol=USD
# ---------------------------------------------------------------------------
AV_SERIES = {
    'WTI': (
        'commodity',
        {'function': 'WTI',         'interval': 'weekly'},
        'USD/barrel'
    ),
    'NATURAL_GAS': (
        'commodity',
        {'function': 'NATURAL_GAS', 'interval': 'weekly'},
        'USD/MMBtu'
    ),
    'GOLD': (
        'fx',
        {'function': 'FX_WEEKLY', 'from_symbol': 'XAU', 'to_symbol': 'USD'},
        'USD/oz troy'
    ),
    'SILVER': (
        'fx',
        {'function': 'FX_WEEKLY', 'from_symbol': 'XAG', 'to_symbol': 'USD'},
        'USD/oz troy'
    ),
    'COPPER': (
        'commodity',
        {'function': 'COPPER',      'interval': 'monthly'},
        'USD/lb'
    ),
    'WHEAT': (
        'commodity',
        {'function': 'WHEAT',       'interval': 'monthly'},
        'USD/bushel'
    ),
    'CORN': (
        'commodity',
        {'function': 'CORN',        'interval': 'monthly'},
        'USD/bushel'
    ),
}

BASE_URL = 'https://www.alphavantage.co/query'


def _parse_date(val: str) -> date | None:
    if not val:
        return None
    try:
        return datetime.strptime(val[:10], '%Y-%m-%d').date()
    except ValueError:
        return None


class CommodityPricePipeline(BasePipeline):
    """
    Pipeline de precios de materias primas desde Alpha Vantage.
    Descarga 7 series en cada ejecución (muy por debajo del límite de 25/día).
    Series semanales (WTI, gas, oro, plata): alineadas con el reporte COT.
    Series mensuales (cobre, trigo, maíz): interpoladas a frecuencia semanal
    para poder usarlas como overlay en los gráficos COT.
    """

    def __init__(self):
        super().__init__()
        load_dotenv()
        self.api_key = os.getenv('ALPHA_VANTAGE_API_KEY')
        if not self.api_key:
            raise ValueError(
                "ALPHA_VANTAGE_API_KEY no encontrada. "
                "Añádela al archivo .env"
            )
        config = SOURCES.get('alpha_vantage', {})
        # Rate limit generoso: 1 req cada 15s para no acercarnos al límite diario
        self.limiter = RateLimiter(min_interval=config.get('rate_limit', 15.0))

    min_interval_hours = 144.0  # Semanal (Alpha Vantage actualiza los lunes)

    @property
    def name(self) -> str:
        return "commodity_prices"

    # ------------------------------------------------------------------
    # EXTRACT — una petición por serie
    # ------------------------------------------------------------------
    def extract(self, since_date=None) -> dict:
        """
        Descarga todas las series. Retorna un dict {series_id: raw_json}.
        since_date se ignora aquí porque AV siempre devuelve el histórico
        completo; el filtrado se hace en transform().
        """
        results = {}

        for series_id, (tipo, params, unit) in AV_SERIES.items():
            self.logger.info(f"Descargando {series_id}...")
            self.limiter.wait()

            request_params = {**params, 'apikey': self.api_key}
            resp = requests.get(BASE_URL, params=request_params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            # Detectar error de API key o rate limit
            if 'Information' in data:
                raise RuntimeError(
                    f"Alpha Vantage responde con aviso: {data['Information']}"
                )
            if 'Note' in data:
                raise RuntimeError(
                    f"Rate limit Alpha Vantage: {data['Note']}"
                )

            results[series_id] = data
            self.logger.info(f"  → {series_id} OK")

        self._save_staging(results)
        return results

    # ------------------------------------------------------------------
    # TRANSFORM
    # ------------------------------------------------------------------
    def transform(self, raw_data: dict) -> list[dict]:
        """
        Parsea cada serie al formato {date, series_id, price, unit}.

        Las series mensuales se interpolan a frecuencia semanal (forward fill)
        para que el overlay en el gráfico COT sea continuo.
        """
        all_records = []

        for series_id, data in raw_data.items():
            tipo, params, unit = AV_SERIES[series_id]
            records = self._parse_series(series_id, tipo, data, unit)

            if not records:
                self.logger.warning(f"Sin datos para {series_id}")
                continue

            # Series mensuales → interpolar a semanal
            interval = params.get('interval', 'weekly')
            if interval == 'monthly':
                records = self._interpolate_to_weekly(records, series_id, unit)

            all_records.extend(records)
            self.logger.info(f"  {series_id}: {len(records)} puntos")

        self.logger.info(
            f"Total transformados: {len(all_records)} registros en "
            f"{len(raw_data)} series"
        )
        return all_records

    def _parse_series(self, series_id: str, tipo: str,
                      data: dict, unit: str) -> list[dict]:
        """Extrae la lista de {date, price} del JSON crudo de AV."""
        records = []

        if tipo == 'commodity':
            # Formato: {"data": [{"date": "2024-01-05", "value": "72.5"}, ...]}
            for point in data.get('data', []):
                d = _parse_date(point.get('date'))
                v = point.get('value', '.')
                if d is None or v == '.' or v is None:
                    continue
                try:
                    records.append({
                        'date':      d,
                        'series_id': series_id,
                        'price':     float(v),
                        'unit':      unit,
                    })
                except (ValueError, TypeError):
                    continue

        elif tipo == 'fx':
            # Formato: {"Weekly Time Series": {"2024-01-05": {"4. close": "2050.3"}, ...}}
            ts_key = next(
                (k for k in data if 'Weekly Time Series' in k or 'Time Series' in k),
                None
            )
            if ts_key is None:
                self.logger.warning(
                    f"No se encontró clave de serie temporal en {series_id}. "
                    f"Keys disponibles: {list(data.keys())}"
                )
                return []

            for date_str, ohlc in data[ts_key].items():
                d = _parse_date(date_str)
                # AV FX usa "4. close" como precio de cierre semanal
                close_key = next((k for k in ohlc if '4.' in k or 'close' in k.lower()), None)
                if d is None or close_key is None:
                    continue
                try:
                    records.append({
                        'date':      d,
                        'series_id': series_id,
                        'price':     float(ohlc[close_key]),
                        'unit':      unit,
                    })
                except (ValueError, TypeError):
                    continue

        return records

    def _interpolate_to_weekly(self, monthly_records: list[dict],
                                series_id: str, unit: str) -> list[dict]:
        """
        Convierte datos mensuales a semanales por forward fill.
        Genera un índice semanal (viernes) y propaga el último precio mensual conocido.
        """
        if not monthly_records:
            return []

        df = pd.DataFrame(monthly_records)
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date').sort_index()

        # Índice semanal desde el primer punto hasta hoy
        weekly_idx = pd.date_range(
            start=df.index.min(),
            end=pd.Timestamp.now(),
            freq='W-FRI'  # viernes, mismo día que el COT
        )

        # Reindex + forward fill
        df_weekly = df['price'].reindex(
            df.index.union(weekly_idx)
        ).sort_index().ffill().reindex(weekly_idx)

        return [
            {
                'date':      d.date(),
                'series_id': series_id,
                'price':     float(p),
                'unit':      unit,
            }
            for d, p in df_weekly.items()
            if pd.notna(p)
        ]

    # ------------------------------------------------------------------
    # LOAD
    # ------------------------------------------------------------------
    def load(self, clean_data: list[dict]) -> int:
        """UPSERT — actualiza precio si ya existe la fecha+serie."""
        if not clean_data:
            return 0

        with get_session() as session:
            for row in clean_data:
                stmt = sqlite_upsert(CommodityPrice).values(**row)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['date', 'series_id'],
                    set_={'price': stmt.excluded.price}
                )
                session.execute(stmt)
            session.commit()

        self.logger.info(f"Cargados {len(clean_data)} precios en commodity_prices.")
        return len(clean_data)