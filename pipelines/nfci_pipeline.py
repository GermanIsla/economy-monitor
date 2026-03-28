# pipelines/nfci_pipeline.py
# Pipeline ETL para el indicador NFCI
# Fuente: FRED API — soporta filtro por fecha (modo incremental)

import os
import requests
from datetime import date
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
from pipelines.base import BasePipeline
from db.engine import get_session
from db.models.nfci import NFCIReading
from utils.rate_limiter import RateLimiter
from config.settings import SOURCES

NFCI_SERIES = {
    'NFCI': 'NFCI (Índice General)',
    'NFCICREDIT': 'NFCI Subíndice de Crédito',
}


class NFCIPipeline(BasePipeline):
    """
    Pipeline del indicador NFCI de la Fed de Chicago.
    La API de FRED soporta filtro por observation_start (modo incremental).
    """

    def __init__(self):
        super().__init__()
        config = SOURCES['nfci']
        self.base_url = config['base_url']
        self.limiter = RateLimiter(min_interval=config['rate_limit'])

        from dotenv import load_dotenv
        load_dotenv()
        self.api_key = os.getenv("FRED_API_KEY")
        if not self.api_key:
            raise ValueError(
                "No se encontró FRED_API_KEY en .env\n"
                "Obtén una clave gratuita en: https://fred.stlouisfed.org/docs/api/api_key.html"
            )

    min_interval_hours = 144.0  # Semanal

    @property
    def name(self) -> str:
        return "nfci"

    def extract(self, since_date: date = None) -> dict[str, list[dict]]:
        """Descarga series NFCI desde FRED, con filtro por fecha si es incremental."""
        all_data = {}

        for series_id, description in NFCI_SERIES.items():
            self.logger.info(f"Descargando serie: {series_id} ({description})")
            self.limiter.wait()

            params = {
                'series_id': series_id,
                'api_key': self.api_key,
                'file_type': 'json',
                'sort_order': 'asc',
            }

            # Filtro incremental
            if since_date:
                params['observation_start'] = since_date.isoformat()
                self.logger.info(f"  Filtro: desde {since_date}")

            resp = requests.get(self.base_url, params=params, timeout=30)
            resp.raise_for_status()

            observations = resp.json().get('observations', [])
            all_data[series_id] = observations
            self.logger.info(f"  → {len(observations)} observaciones")

        return all_data

    @staticmethod
    def _parse_date(date_str: str) -> date | None:
        if not date_str or not isinstance(date_str, str):
            return None
        try:
            return date.fromisoformat(date_str.strip())
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _parse_value(value_str: str) -> float | None:
        if not value_str or value_str.strip() == '.':
            return None
        try:
            return float(value_str)
        except (ValueError, TypeError):
            return None

    def transform(self, raw_data: dict[str, list[dict]]) -> list[dict]:
        """Limpia datos de FRED."""
        clean = []
        discarded = 0

        for series_id, observations in raw_data.items():
            for obs in observations:
                obs_date = self._parse_date(obs.get('date'))
                obs_value = self._parse_value(obs.get('value'))

                if obs_date is None or obs_value is None:
                    discarded += 1
                    continue

                clean.append({
                    'date': obs_date,
                    'indicator_name': series_id,
                    'value': obs_value,
                })

        self.logger.info(f"Transformación: {len(clean)} válidos, {discarded} descartados")
        return clean

    def load(self, clean_data: list[dict]) -> int:
        """UPSERT por date + indicator_name."""
        with get_session() as session:
            for row in clean_data:
                stmt = sqlite_upsert(NFCIReading).values(**row)
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=['date', 'indicator_name']
                )
                session.execute(stmt)
            session.commit()
        return len(clean_data)