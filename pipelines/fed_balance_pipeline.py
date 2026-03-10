# pipelines/fed_balance_pipeline.py
# Pipeline ETL: Balance Sheet de la Reserva Federal (FRED API)
# Series: TREAST, FEDDT, WSHOMCB — datos semanales del H.4.1

import json
import requests
from datetime import date, datetime
from sqlalchemy.dialects.sqlite import insert

from pipelines.base import BasePipeline
from db.models.fed_balance import FedBalanceAsset
from db.engine import get_session
from config.settings import SOURCES
import os
from utils.rate_limiter import RateLimiter

# Mapeo series_id → nombre descriptivo en español
FED_BALANCE_SERIES = {
    "TREAST": "Bonos del Tesoro de EE.UU.",
    "FEDDT": "Deuda de Agencias Federales",
    "WSHOMCB": "Valores Respaldados por Hipotecas (MBS)",
}


class FedBalancePipeline(BasePipeline):
    """
    Descarga las tres series del balance sheet de la Fed desde FRED.
    Datos del H.4.1 — nivel semanal (miércoles), en miles de millones de USD.
    """

    def __init__(self):
        super().__init__()
        config = SOURCES.get("fred", {})
        self.limiter = RateLimiter(min_interval=config['rate_limit'])

        from dotenv import load_dotenv
        load_dotenv()
        self.api_key = os.getenv("FRED_API_KEY")
        if not self.api_key:
            self.logger.error("FRED_API_KEY no encontrada en .env")
        self.base_url = "https://api.stlouisfed.org/fred/series/observations"

    @property
    def name(self) -> str:
        return "fed_balance"

    # ------------------------------------------------------------------
    # EXTRACT
    # ------------------------------------------------------------------
    def extract(self, since_date: date | None = None, full: bool = False) -> dict:
        """
        Descarga observaciones de cada serie desde FRED.
        Retorna un dict {series_id: [{"date": ..., "value": ...}, ...]}
        """
        if not self.api_key:
            self.logger.error("FRED_API_KEY no encontrada en .env")
            raise ValueError("FRED_API_KEY no configurada")

        all_data = {}

        for series_id in FED_BALANCE_SERIES:
            params = {
                "series_id": series_id,
                "api_key": self.api_key,
                "file_type": "json",
                "sort_order": "asc",
                "observation_start": "2002-01-01",  # Histórico completo
            }

            if since_date and not full:
                params["observation_start"] = since_date.isoformat()

            self.logger.info(f"Descargando serie {series_id} desde FRED...")
            self.limiter.wait()

            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()
            observations = data.get("observations", [])

            # Filtrar puntos sin valor válido ("." es el marcador de FRED para N/A)
            valid = [
                {"date": obs["date"], "value": float(obs["value"])}
                for obs in observations
                if obs.get("value", ".") != "."
            ]

            all_data[series_id] = valid
            self.logger.info(f"  → {len(valid)} observaciones obtenidas para {series_id}")

        # Guardar en staging
        self._save_staging(json.dumps(all_data, default=str).encode())
        return all_data

    # ------------------------------------------------------------------
    # TRANSFORM
    # ------------------------------------------------------------------
    def transform(self, raw_data: dict) -> list[dict]:
        """
        Normaliza las observaciones en una lista plana de dicts listos para insertar.
        """
        records = []
        for series_id, observations in raw_data.items():
            series_name = FED_BALANCE_SERIES.get(series_id, series_id)
            for obs in observations:
                try:
                    records.append({
                        "date": datetime.strptime(obs["date"], "%Y-%m-%d").date(),
                        "series_id": series_id,
                        "series_name": series_name,
                        "value": float(obs["value"]),
                    })
                except (ValueError, KeyError) as e:
                    self.logger.warning(f"Registro inválido en {series_id}: {obs} — {e}")

        self.logger.info(f"transform(): {len(records)} registros válidos")
        return records

    # ------------------------------------------------------------------
    # LOAD
    # ------------------------------------------------------------------
    def load(self, records: list[dict]) -> int:
        """
        Inserta o ignora duplicados (UPSERT por date + series_id).
        Retorna el número de filas insertadas.
        """
        if not records:
            self.logger.warning("No hay registros para cargar")
            return 0

        with get_session() as session:
            stmt = insert(FedBalanceAsset).values(records)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["date", "series_id"]
            )
            result = session.execute(stmt)
            session.commit()

        inserted = result.rowcount
        self.logger.info(f"load(): {inserted} filas nuevas insertadas en fed_balance_assets")
        return inserted

    # ------------------------------------------------------------------
    # FROM STAGING
    # ------------------------------------------------------------------
    def _load_from_staging_bytes(self, raw_bytes: bytes) -> dict:
        """Reconstruye el dict a partir de los bytes JSON del staging."""
        return json.loads(raw_bytes.decode())
