# pipelines/repo_pipeline.py
# Pipeline ETL para datos de Repo Tri-Party — TODAS las hojas del Excel
# Fuente: Federal Reserve Bank of New York

import io
import os
import requests
import pandas as pd
from datetime import date, datetime
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
from pipelines.base import BasePipeline, STAGING_DIR
from db.engine import get_session
from db.models.repo import RepoOperation
from db.models.gcf_repo import GCFRepoTotal, RepoMarketSplit, GCFRepoAssetClass, GCFRepoCUSIP
from utils.rate_limiter import RateLimiter
from config.settings import SOURCES


class RepoPipeline(BasePipeline):

    URL_POST_NOV2025 = (
        "https://www.newyorkfed.org/medialibrary/Research/Interactives/"
        "Data/tri-party-repo/tri-party-repo_data"
    )
    URL_PRE_NOV2025 = (
        "https://www.newyorkfed.org/medialibrary/Research/Interactives/"
        "Data/tri-party-repo/tri-party-repo-preNov25_data"
    )

    def __init__(self):
        super().__init__()
        config = SOURCES.get('repo', {})
        self.limiter = RateLimiter(min_interval=config.get('rate_limit', 2.0))

    @property
    def name(self) -> str:
        return "repo_operations"

    # ================================================================
    # Extract
    # ================================================================
    def _download_excel(self, url: str, label: str) -> bytes | None:
        try:
            self.limiter.wait()
            self.logger.info(f"Descargando {label}...")
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            self.logger.info(f"  → {len(resp.content) / (1024*1024):.1f} MB")
            return resp.content
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error descargando {label}: {e}")
            return None

    def extract(self, since_date: date = None) -> dict:
        result = {}
        post = self._download_excel(self.URL_POST_NOV2025, "datos post-Nov2025")
        if post:
            result['post'] = post

        cutoff = date(2025, 11, 1)
        if since_date is None or since_date < cutoff:
            pre = self._download_excel(self.URL_PRE_NOV2025, "datos pre-Nov2025")
            if pre:
                result['pre'] = pre
        else:
            self.logger.info("Saltando datos pre-Nov2025")

        if not result:
            raise ConnectionError("No se pudo descargar de la NY Fed")
        return result

    # ================================================================
    # Staging overrides
    # ================================================================
    def _save_staging(self, raw_data) -> str:
        timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        for key, content in raw_data.items():
            fp = os.path.join(STAGING_DIR, f"{self.name}_{key}_{timestamp}.xlsx")
            try:
                with open(fp, 'wb') as f:
                    f.write(content)
            except Exception as e:
                self.logger.warning(f"Staging {key}: {e}")
        self._cleanup_staging()
        return timestamp

    def _cleanup_staging(self, keep: int = 6):
        try:
            prefix = f"{self.name}_"
            files = sorted([f for f in os.listdir(STAGING_DIR) if f.startswith(prefix) and f.endswith('.xlsx')])
            for old in files[:-keep]:
                os.remove(os.path.join(STAGING_DIR, old))
        except Exception:
            pass

    def load_from_staging(self, filepath: str = None) -> dict:
        all_files = sorted([f for f in os.listdir(STAGING_DIR) if f.startswith(f"{self.name}_") and f.endswith('.xlsx')])
        if not all_files:
            raise FileNotFoundError(f"No hay staging para '{self.name}'")
        result = {}
        for key in ['post', 'pre']:
            matching = [f for f in all_files if f"_{key}_" in f]
            if matching:
                fpath = os.path.join(STAGING_DIR, matching[-1])
                with open(fpath, 'rb') as f:
                    result[key] = f.read()
        if not result:
            raise FileNotFoundError("No se encontraron archivos staging válidos")
        return result

    # ================================================================
    # Parsing genérico de hojas
    # ================================================================
    def _find_header_row(self, df_raw: pd.DataFrame, first_col_value: str = 'date') -> int | None:
        """Busca la fila que contiene los headers."""
        for idx, row in df_raw.iterrows():
            val = str(row.iloc[0]).lower().strip() if pd.notna(row.iloc[0]) else ''
            if val == first_col_value:
                return idx
        return None

    def _read_sheet(self, excel_bytes: bytes, sheet_name: str, expected_cols: list[str]) -> pd.DataFrame:
        """
        Lee una hoja del Excel con detección automática de headers.
        Retorna DataFrame vacío si la hoja no existe o no tiene datos.
        """
        try:
            df_raw = pd.read_excel(
                io.BytesIO(excel_bytes), sheet_name=sheet_name,
                header=None, engine='openpyxl'
            )
        except (ValueError, KeyError):
            self.logger.info(f"  Hoja '{sheet_name}' no encontrada, saltando")
            return pd.DataFrame()

        header_row = self._find_header_row(df_raw)
        if header_row is None:
            self.logger.warning(f"  No se encontraron headers en '{sheet_name}'")
            return pd.DataFrame()

        df = df_raw.iloc[header_row + 1:].copy()
        df.columns = list(df_raw.iloc[header_row])
        df.reset_index(drop=True, inplace=True)
        df.dropna(how='all', inplace=True)

        # Renombrar a nombres esperados
        col_list = list(df.columns)
        rename = {}
        for i, col in enumerate(col_list):
            if i < len(expected_cols) and col != expected_cols[i]:
                rename[col] = expected_cols[i]
        if rename:
            df.rename(columns=rename, inplace=True)

        # Deduplicar columnas
        if df.columns.duplicated().any():
            df = df.loc[:, ~df.columns.duplicated(keep='first')]

        # Convertir fecha
        if 'date' in df.columns:
            df['date'] = pd.to_numeric(df['date'], errors='coerce')
            df['date'] = pd.to_datetime(df['date'].astype('Int64').astype(str), format='%Y%m%d', errors='coerce')
            df.dropna(subset=['date'], inplace=True)

        return df

    # ================================================================
    # Transform — cada hoja por separado
    # ================================================================
    def _transform_volume_haircut(self, excel_bytes: bytes, label: str) -> list[dict]:
        """Hoja volume_haircut_concentration → tabla repo_operations."""
        expected = ["date", "group_id", "group_name", "collateral_value", "share_of_total",
                    "top_3_concentration", "p10", "median", "p90", "fedwire", "num_obs", "margin_stdev"]
        df = self._read_sheet(excel_bytes, 'volume_haircut_concentration', expected)
        if df.empty:
            return []

        for col in ['collateral_value', 'share_of_total', 'top_3_concentration',
                     'p10', 'median', 'p90', 'fedwire', 'num_obs', 'margin_stdev']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        df = df.dropna(subset=['group_name'])
        df['collateral_value'] = pd.to_numeric(df.get('collateral_value', 0), errors='coerce')
        df = df[df['collateral_value'] > 0]

        clean = []
        for _, r in df.iterrows():
            clean.append({
                'date': r['date'].date(),
                'group_id': int(r['group_id']) if pd.notna(r.get('group_id')) else None,
                'group_name': str(r['group_name']).strip(),
                'collateral_value': float(r['collateral_value']),
                'share_of_total': float(r['share_of_total']) if pd.notna(r.get('share_of_total')) else None,
                'top_3_concentration': float(r['top_3_concentration']) if pd.notna(r.get('top_3_concentration')) else None,
                'margin_p10': float(r['p10']) if pd.notna(r.get('p10')) else None,
                'margin_median': float(r['median']) if pd.notna(r.get('median')) else None,
                'margin_p90': float(r['p90']) if pd.notna(r.get('p90')) else None,
                'fedwire_eligible': float(r['fedwire']) if pd.notna(r.get('fedwire')) else None,
                'num_observations': int(r['num_obs']) if pd.notna(r.get('num_obs')) else None,
                'margin_stdev': float(r['margin_stdev']) if pd.notna(r.get('margin_stdev')) else None,
            })
        self.logger.info(f"  volume_haircut: {len(clean)} registros de {label}")
        return clean

    def _transform_gcf_total(self, excel_bytes: bytes, label: str) -> list[dict]:
        """Hoja gcf_repo_total → tabla gcf_repo_total."""
        expected = ["date", "metric_type", "value"]
        df = self._read_sheet(excel_bytes, 'gcf_repo_total', expected)
        if df.empty:
            return []

        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        df = df.dropna(subset=['metric_type', 'value'])

        clean = []
        for _, r in df.iterrows():
            clean.append({
                'date': r['date'].date(),
                'metric_type': str(r['metric_type']).strip(),
                'value': float(r['value']),
            })
        self.logger.info(f"  gcf_total: {len(clean)} registros de {label}")
        return clean

    def _transform_triparty_gcf(self, excel_bytes: bytes, label: str) -> list[dict]:
        """Hoja triparty_gcf → tabla repo_market_split."""
        expected = ["date", "collateral_type", "tpr_value", "tpr_share", "gcf_value", "gcf_share"]
        df = self._read_sheet(excel_bytes, 'triparty_gcf', expected)
        if df.empty:
            return []

        for col in ['tpr_value', 'tpr_share', 'gcf_value', 'gcf_share']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        df = df.dropna(subset=['collateral_type'])

        clean = []
        for _, r in df.iterrows():
            clean.append({
                'date': r['date'].date(),
                'collateral_type': str(r['collateral_type']).strip(),
                'tpr_value': float(r['tpr_value']) if pd.notna(r.get('tpr_value')) else None,
                'tpr_share': float(r['tpr_share']) if pd.notna(r.get('tpr_share')) else None,
                'gcf_value': float(r['gcf_value']) if pd.notna(r.get('gcf_value')) else None,
                'gcf_share': float(r['gcf_share']) if pd.notna(r.get('gcf_share')) else None,
            })
        self.logger.info(f"  triparty_gcf: {len(clean)} registros de {label}")
        return clean

    def _transform_asset_classes(self, excel_bytes: bytes, label: str) -> list[dict]:
        """Hoja gcf_repo_asset_classes → tabla gcf_repo_asset_classes."""
        expected = ["date", "collateral_type", "overnight", "overnight_share", "term", "term_share"]
        df = self._read_sheet(excel_bytes, 'gcf_repo_asset_classes', expected)
        if df.empty:
            return []

        for col in ['overnight', 'overnight_share', 'term', 'term_share']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        df = df.dropna(subset=['collateral_type'])

        clean = []
        for _, r in df.iterrows():
            clean.append({
                'date': r['date'].date(),
                'collateral_type': str(r['collateral_type']).strip(),
                'overnight': float(r['overnight']) if pd.notna(r.get('overnight')) else None,
                'overnight_share': float(r['overnight_share']) if pd.notna(r.get('overnight_share')) else None,
                'term': float(r['term']) if pd.notna(r.get('term')) else None,
                'term_share': float(r['term_share']) if pd.notna(r.get('term_share')) else None,
            })
        self.logger.info(f"  asset_classes: {len(clean)} registros de {label}")
        return clean

    def _transform_cusips(self, excel_bytes: bytes, label: str) -> list[dict]:
        """Hoja gcf_repo_gcf_cusips → tabla gcf_repo_cusips."""
        expected = ["date", "collateral_type", "overnight", "overnight_share", "term", "term_share"]
        df = self._read_sheet(excel_bytes, 'gcf_repo_gcf_cusips', expected)
        if df.empty:
            return []

        for col in ['overnight', 'overnight_share', 'term', 'term_share']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        df = df.dropna(subset=['collateral_type'])

        clean = []
        for _, r in df.iterrows():
            clean.append({
                'date': r['date'].date(),
                'collateral_type': str(r['collateral_type']).strip(),
                'overnight': float(r['overnight']) if pd.notna(r.get('overnight')) else None,
                'overnight_share': float(r['overnight_share']) if pd.notna(r.get('overnight_share')) else None,
                'term': float(r['term']) if pd.notna(r.get('term')) else None,
                'term_share': float(r['term_share']) if pd.notna(r.get('term_share')) else None,
            })
        self.logger.info(f"  cusips: {len(clean)} registros de {label}")
        return clean

    # ================================================================
    # Transform principal — combina todos los Excel y todas las hojas
    # ================================================================
    def transform(self, raw_data: dict) -> dict:
        """
        Procesa TODAS las hojas de ambos Excel.
        Retorna un dict con listas de datos por tabla destino.
        """
        all_results = {
            'volume_haircut': [],
            'gcf_total': [],
            'triparty_gcf': [],
            'asset_classes': [],
            'cusips': [],
        }

        for key in ['pre', 'post']:
            if key not in raw_data:
                continue
            label = f"{key}-Nov2025"
            excel = raw_data[key]

            all_results['volume_haircut'].extend(self._transform_volume_haircut(excel, label))
            all_results['gcf_total'].extend(self._transform_gcf_total(excel, label))
            all_results['triparty_gcf'].extend(self._transform_triparty_gcf(excel, label))
            all_results['asset_classes'].extend(self._transform_asset_classes(excel, label))
            all_results['cusips'].extend(self._transform_cusips(excel, label))

        # Deduplicar cada conjunto
        for table_key in all_results:
            data = all_results[table_key]
            if not data:
                continue
            df_tmp = pd.DataFrame(data)
            if 'group_name' in df_tmp.columns:
                dedup_cols = ['date', 'group_name']
            elif 'metric_type' in df_tmp.columns:
                dedup_cols = ['date', 'metric_type']
            elif 'collateral_type' in df_tmp.columns:
                dedup_cols = ['date', 'collateral_type']
            else:
                continue
            df_tmp.drop_duplicates(subset=dedup_cols, keep='last', inplace=True)
            all_results[table_key] = df_tmp.to_dict('records')

        total = sum(len(v) for v in all_results.values())
        self.logger.info(f"Total combinado: {total} registros en 5 tablas")
        return all_results

    # ================================================================
    # Load — carga cada tabla por separado
    # ================================================================
    def _upsert_batch(self, session, model, data: list[dict], conflict_cols: list[str]):
        """UPSERT genérico por lotes."""
        for row in data:
            stmt = sqlite_upsert(model).values(**row)
            stmt = stmt.on_conflict_do_nothing(index_elements=conflict_cols)
            session.execute(stmt)

    def load(self, all_data: dict) -> int:
        """Carga todas las tablas."""
        total = 0
        batch_size = 500

        table_config = [
            ('volume_haircut', RepoOperation, ['date', 'group_name']),
            ('gcf_total', GCFRepoTotal, ['date', 'metric_type']),
            ('triparty_gcf', RepoMarketSplit, ['date', 'collateral_type']),
            ('asset_classes', GCFRepoAssetClass, ['date', 'collateral_type']),
            ('cusips', GCFRepoCUSIP, ['date', 'collateral_type']),
        ]

        with get_session() as session:
            for table_key, model, conflict_cols in table_config:
                data = all_data.get(table_key, [])
                if not data:
                    continue

                for i in range(0, len(data), batch_size):
                    batch = data[i:i + batch_size]
                    self._upsert_batch(session, model, batch, conflict_cols)
                    session.commit()

                self.logger.info(f"  {table_key}: {len(data)} registros cargados")
                total += len(data)

        return total