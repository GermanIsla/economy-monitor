# pipelines/treasury_pipeline.py
# Pipeline ETL para subastas del Tesoro de EE.UU.
# Fuente: FiscalData API — soporta filtro por fecha (modo incremental)

import requests
import math
from datetime import date
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
from pipelines.base import BasePipeline
from db.engine import get_session
from db.models.treasury import TreasuryAuction
from utils.rate_limiter import RateLimiter
from config.settings import SOURCES


class TreasuryPipeline(BasePipeline):
    """
    Pipeline de subastas del Tesoro de EE.UU.
    
    La API de FiscalData soporta filtro por fecha, así que el modo
    incremental descarga solo las subastas nuevas desde la última ejecución.
    """

    def __init__(self):
        super().__init__()
        config = SOURCES['treasury']
        self.base_url = config['base_url']
        self.limiter = RateLimiter(min_interval=config['rate_limit'])

    @property
    def name(self) -> str:
        return "treasury_auctions"

    def extract(self, since_date: date = None) -> list[dict]:
        """
        Descarga subastas desde FiscalData con paginación.
        Si since_date se proporciona, filtra por issue_date >= since_date.
        """
        all_data = []
        page = 1
        page_size = 100

        params = {
            'page[number]': page,
            'page[size]': page_size,
            'sort': 'issue_date',
        }

        # Filtro incremental: solo datos nuevos
        if since_date:
            params['filter'] = f'issue_date:gte:{since_date.isoformat()}'
            self.logger.info(f"Filtro API: issue_date >= {since_date}")

        # Primera llamada
        self.limiter.wait()
        resp = requests.get(self.base_url, params=params, timeout=30)
        resp.raise_for_status()
        result = resp.json()

        total_count = result['meta']['total-count']

        if total_count == 0:
            self.logger.info("La API no devolvió datos nuevos.")
            return []

        total_pages = math.ceil(total_count / page_size)
        all_data.extend(result['data'])
        self.logger.info(f"Total: {total_count} registros en {total_pages} páginas")

        # Páginas restantes
        for page in range(2, total_pages + 1):
            self.limiter.wait()
            params['page[number]'] = page
            resp = requests.get(self.base_url, params=params, timeout=30)
            resp.raise_for_status()
            all_data.extend(resp.json()['data'])

            if page % 50 == 0:
                self.logger.info(f"Progreso: página {page}/{total_pages}")

        self.logger.info(f"Extracción completada: {len(all_data)} registros")
        return all_data

    @staticmethod
    def _parse_date(date_str: str) -> date | None:
        """Convierte string 'YYYY-MM-DD' a objeto date."""
        if not date_str or not isinstance(date_str, str):
            return None
        try:
            return date.fromisoformat(date_str.strip())
        except (ValueError, AttributeError):
            return None

    def transform(self, raw_data: list[dict]) -> list[dict]:
        """Filtra por tipos deseados y convierte tipos."""
        clean = []
        valid_types = {'Bill', 'Note', 'Bond'}
        discarded = 0

        for row in raw_data:
            sec_type = row.get('security_type', '')
            if sec_type not in valid_types:
                discarded += 1
                continue

            issue_date = self._parse_date(row.get('issue_date'))
            maturity_date = self._parse_date(row.get('maturity_date'))
            if issue_date is None or maturity_date is None:
                discarded += 1
                continue

            try:
                total = float(row.get('total_accepted', 0))
                if total <= 0:
                    discarded += 1
                    continue
            except (ValueError, TypeError):
                discarded += 1
                continue

            clean.append({
                'issue_date': issue_date,
                'maturity_date': maturity_date,
                'security_type': sec_type,
                'security_term': row.get('security_term'),
                'total_accepted': total,
            })

        self.logger.info(f"Transformación: {len(clean)} válidos, {discarded} descartados")
        return clean

    def load(self, clean_data: list[dict]) -> int:
        """UPSERT por lotes."""
        batch_size = 500
        loaded = 0

        with get_session() as session:
            for i in range(0, len(clean_data), batch_size):
                batch = clean_data[i:i + batch_size]
                for row in batch:
                    stmt = sqlite_upsert(TreasuryAuction).values(**row)
                    stmt = stmt.on_conflict_do_nothing(
                        index_elements=['issue_date', 'security_type', 'maturity_date']
                    )
                    session.execute(stmt)
                session.commit()
                loaded += len(batch)

                if loaded % 2000 == 0:
                    self.logger.info(f"Carga: {loaded}/{len(clean_data)} registros")

        return len(clean_data)