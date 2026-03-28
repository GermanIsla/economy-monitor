# pipelines/cot_pipeline.py
# Pipeline COT: descarga el reporte Disaggregated Combined de la CFTC vía Socrata API

import json
import os
from datetime import date, datetime
from pathlib import Path

import requests
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert

from config.settings import SOURCES
from db.engine import get_session
from db.models.cot import COTReport
from pipelines.base import BasePipeline
from utils.rate_limiter import RateLimiter

# ---------------------------------------------------------------------------
# Contratos objetivo y su categoría
# Clave: valor exacto del campo 'commodity_name' en la API de la CFTC.
# Si añades un contrato nuevo, verifica el nombre exacto consultando:
#   https://publicreporting.cftc.gov/resource/kh3c-gbw2.json?$limit=5&$select=commodity_name,contract_market_name&$where=commodity_name like '%CRUDE%'
# ---------------------------------------------------------------------------

COT_COMMODITY_GROUPS = {
    # Energía
    'WTI-PHYSICAL':                'energy',   # contrato principal WTI (1030 semanas)
    'CRUDE OIL, LIGHT SWEET-WTI':  'energy',   # nombre alternativo histórico
    'NAT GAS NYME':                'energy',   # gas natural NYMEX
    'HENRY HUB':                   'energy',   # Henry Hub
    'HENRY HUB PENULTIMATE NAT GAS': 'energy', # penúltimo contrato HH
    'NO. 2 HEATING OIL':           'energy',
    'GASOLINE BLENDSTOCK (RBOB)':  'energy',
    # Metales
    'GOLD':                        'metals',
    'SILVER':                      'metals',
    'COPPER- #1':                  'metals',   # era COPPER-GRADE #1
    'PLATINUM':                    'metals',
    'PALLADIUM':                   'metals',
    # Granos
    'WHEAT-SRW':                   'grains',
    'WHEAT-HRW':                   'grains',
    'WHEAT-HRSpring':              'grains',   # trigo de primavera
    'CORN':                        'grains',
    'SOYBEANS':                    'grains',
    'SOYBEAN OIL':                 'grains',
    'SOYBEAN MEAL':                'grains',
}
# Nombres genéricos para el filtro $where de la API (commodity_name)
_COMMODITY_NAMES_API = {
    'CRUDE OIL', 'NATURAL GAS', 'HENRY HUB NAT GAS',
    'NO. 2 HEATING OIL', 'GASOLINE BLENDSTOCK (RBOB)',
    'GOLD', 'SILVER', 'COPPER', 'PLATINUM', 'PALLADIUM',
    'CORN', 'WHEAT', 'SOYBEANS', 'SOYBEAN OIL', 'SOYBEAN MEAL',
}

_COMMODITY_NAMES_FILTER = ",".join(f"'{n}'" for n in _COMMODITY_NAMES_API)


def _safe_int(val) -> int | None:
    """Convierte un valor de la API (string o None) a entero."""
    if val is None or val == '':
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _parse_date(val: str) -> date | None:
    """Parsea la fecha ISO de la API a objeto date de Python."""
    if not val:
        return None
    try:
        return datetime.strptime(val[:10], '%Y-%m-%d').date()
    except ValueError:
        return None


class COTPipeline(BasePipeline):
    """
    Pipeline de Commitments of Traders (COT) — Disaggregated Combined.
    Fuente: CFTC Public Reporting Environment (Socrata API).
    Dataset: kh3c-gbw2 — futuros y opciones combinados.
    Publicación: viernes ~15:30 ET con datos del martes anterior.
    Histórico: desde 2006-06-13.
    """

    # Fecha de inicio del histórico Disaggregated
    HISTORY_START = '2006-06-13'

    def __init__(self):
        super().__init__()
        config = SOURCES.get('cot', {})
        self.base_url = config.get('base_url',
            'https://publicreporting.cftc.gov/resource/kh3c-gbw2.json')
        self.page_size = config.get('page_size', 1000)
        self.limiter = RateLimiter(min_interval=config.get('rate_limit', 1.0))

    min_interval_hours = 144.0  # Semanal (CFTC publica los viernes)

    @property
    def name(self) -> str:
        return "cot"

    # ------------------------------------------------------------------
    # EXTRACT
    # ------------------------------------------------------------------
    def extract(self, since_date=None) -> list[dict]:
        """
        Descarga registros COT de la API Socrata con paginación.

        En modo incremental (since_date != None y full=False),
        filtra por fecha para descargar solo semanas nuevas.
        En modo --full, descarga todo el histórico desde 2006-06-13.
        """
        # Construir filtro de fecha
        if since_date is None:
            date_filter = f"report_date_as_yyyy_mm_dd >= '{self.HISTORY_START}'"
            self.logger.info(f"Modo completo: descargando desde {self.HISTORY_START}")
        else:
            date_str = since_date.strftime('%Y-%m-%d')
            date_filter = f"report_date_as_yyyy_mm_dd > '{date_str}'"
            self.logger.info(f"Modo incremental: desde {date_str}")

        # Filtro combinado: fecha + commodities objetivo
        where_clause = (
            f"{date_filter} AND "
            f"commodity_name in({_COMMODITY_NAMES_FILTER})"
        )

        all_records = []
        offset = 0

        while True:
            self.limiter.wait()
            params = {
                '$limit':  self.page_size,
                '$offset': offset,
                '$where':  where_clause,
                '$order':  'report_date_as_yyyy_mm_dd ASC',
            }

            resp = requests.get(self.base_url, params=params, timeout=30)
            resp.raise_for_status()
            batch = resp.json()

            if not batch:
                break

            all_records.extend(batch)
            offset += len(batch)

            if offset % 5000 == 0:
                self.logger.info(f"Descargados {offset} registros...")

            # Si la página está incompleta, hemos llegado al final
            if len(batch) < self.page_size:
                break

        self.logger.info(f"Total descargados: {len(all_records)} registros")

        # Guardar en staging para poder re-procesar sin re-descargar
        self._save_staging(all_records)

        return all_records

    # ------------------------------------------------------------------
    # TRANSFORM
    # ------------------------------------------------------------------
    def transform(self, raw_data: list[dict]) -> list[dict]:
        """
        Limpia y normaliza los datos crudos de la API.

        La API Socrata devuelve todos los valores como strings,
        incluyendo los numéricos. Aquí los convertimos a int/date.
        También asignamos la categoría (energy/metals/grains).
        """
        clean = []
        unknown_commodities = set()

        for row in raw_data:
            contract = row.get('contract_market_name', '').strip()
            commodity = row.get('commodity_name', '').strip().upper()
            group = COT_COMMODITY_GROUPS.get(contract)

            if group is None:
                # Ignorar silenciosamente — son contratos derivados (opciones, spreads, basis)
                # que no nos interesan pero comparten commodity_name con los contratos objetivo
                continue

            report_date = _parse_date(row.get('report_date_as_yyyy_mm_dd'))
            if report_date is None:
                continue

            clean.append({
                'report_date':               report_date,
                'contract_market_name':      contract,
                'cftc_contract_market_code': row.get('cftc_contract_market_code', '').strip(),
                'commodity_name':            commodity,
                'commodity_group':           group,
                # Open interest
                'open_interest':             _safe_int(row.get('open_interest_all')),
                # Producer / Merchant  — sin sufijo _all
                'prod_merc_long':            _safe_int(row.get('prod_merc_positions_long')),
                'prod_merc_short':           _safe_int(row.get('prod_merc_positions_short')),
                # Swap Dealers — doble guión bajo en short/spread (correcto, ya estaba bien)
                'swap_long':                 _safe_int(row.get('swap_positions_long_all')),
                'swap_short':                _safe_int(row.get('swap__positions_short_all')),
                'swap_spread':               _safe_int(row.get('swap__positions_spread_all')),
                # Managed Money — spread sin sufijo _all
                'm_money_long':              _safe_int(row.get('m_money_positions_long_all')),
                'm_money_short':             _safe_int(row.get('m_money_positions_short_all')),
                'm_money_spread':            _safe_int(row.get('m_money_positions_spread')),
                # Other Reportable — sin sufijo _all
                'other_rept_long':           _safe_int(row.get('other_rept_positions_long')),
                'other_rept_short':          _safe_int(row.get('other_rept_positions_short')),
                'other_rept_spread':         _safe_int(row.get('other_rept_positions_spread')),
                # Non-Reportable — correcto
                'nonrept_long':              _safe_int(row.get('nonrept_positions_long_all')),
                'nonrept_short':             _safe_int(row.get('nonrept_positions_short_all')),
                # Cambios semanales — sin sufijo _all en prod_merc
                'change_open_interest':      _safe_int(row.get('change_in_open_interest_all')),
                'change_prod_merc_long':     _safe_int(row.get('change_in_prod_merc_long')),
                'change_prod_merc_short':    _safe_int(row.get('change_in_prod_merc_short')),
                'change_swap_long':          _safe_int(row.get('change_in_swap_long_all')),
                'change_swap_short':         _safe_int(row.get('change_in_swap_short_all')),
                'change_m_money_long':       _safe_int(row.get('change_in_m_money_long_all')),
                'change_m_money_short':      _safe_int(row.get('change_in_m_money_short_all')),
            })

        ignored = len(raw_data) - len(clean)
        if ignored > 0:
            self.logger.info(
                f"Ignorados {ignored} registros (contratos derivados fuera de scope: "
                f"opciones, spreads, basis, contratos menores)."
            )

        self.logger.info(
            f"Transformados: {len(clean)} registros válidos de {len(raw_data)} totales"
        )
        return clean

    # ------------------------------------------------------------------
    # LOAD
    # ------------------------------------------------------------------
    def load(self, clean_data: list[dict]) -> int:
        """Inserta registros con UPSERT — ignora duplicados."""
        if not clean_data:
            self.logger.warning("No hay datos para cargar.")
            return 0

        with get_session() as session:
            for row in clean_data:
                stmt = sqlite_upsert(COTReport).values(**row)
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=['report_date', 'cftc_contract_market_code']
                )
                session.execute(stmt)
            session.commit()

        self.logger.info(f"Cargados {len(clean_data)} registros en cot_reports.")
        return len(clean_data)