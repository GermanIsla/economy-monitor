# pipelines/repo_pipeline.py
# Pipeline ETL para datos de Repo Tri-Party
# Fuente: Federal Reserve Bank of New York
#
# Dos archivos Excel:
# - Pre-Nov2025: histórico mayo 2010 — octubre 2025
# - Post-Nov2025: noviembre 2025 en adelante
# Ambos pueden tener formatos ligeramente distintos (filas de presentación, etc.)

import io
import os
import requests
import pandas as pd
from datetime import date, datetime
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
from pipelines.base import BasePipeline, STAGING_DIR
from db.engine import get_session
from db.models.repo import RepoOperation
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

    EXPECTED_COLUMNS = [
        "date", "group_id", "group_name", "collateral_value", "share_of_total",
        "top_3_concentration", "p10", "median", "p90", "fedwire",
        "num_obs", "margin_stdev"
    ]

    def __init__(self):
        super().__init__()
        config = SOURCES.get('repo', {})
        self.limiter = RateLimiter(min_interval=config.get('rate_limit', 2.0))

    @property
    def name(self) -> str:
        return "repo_operations"

    def _download_excel(self, url: str, label: str) -> bytes | None:
        try:
            self.limiter.wait()
            self.logger.info(f"Descargando {label}...")
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            size_mb = len(resp.content) / (1024 * 1024)
            self.logger.info(f"  → {size_mb:.1f} MB descargados")
            return resp.content
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error descargando {label}: {e}")
            return None

    def extract(self, since_date: date = None) -> dict:
        result = {}
        post_data = self._download_excel(self.URL_POST_NOV2025, "datos post-Nov2025")
        if post_data:
            result['post'] = post_data

        cutoff = date(2025, 11, 1)
        if since_date is None or since_date < cutoff:
            pre_data = self._download_excel(self.URL_PRE_NOV2025, "datos pre-Nov2025 (histórico)")
            if pre_data:
                result['pre'] = pre_data
        else:
            self.logger.info("Saltando datos pre-Nov2025 (ya tenemos datos posteriores)")

        if not result:
            raise ConnectionError("No se pudo descargar ningún archivo de la NY Fed")
        return result

    # --- Staging ---
    def _save_staging(self, raw_data) -> str:
        timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        saved = []
        for key, content in raw_data.items():
            filename = f"{self.name}_{key}_{timestamp}.xlsx"
            filepath = os.path.join(STAGING_DIR, filename)
            try:
                with open(filepath, 'wb') as f:
                    f.write(content)
                saved.append(filename)
            except Exception as e:
                self.logger.warning(f"No se pudo guardar staging {key}: {e}")
        if saved:
            self.logger.info(f"Staging guardado: {', '.join(saved)}")
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
            raise FileNotFoundError(f"No hay archivos de staging para '{self.name}'")
        result = {}
        for key in ['post', 'pre']:
            matching = [f for f in all_files if f"_{key}_" in f]
            if matching:
                fpath = os.path.join(STAGING_DIR, matching[-1])
                self.logger.info(f"Cargando {key} desde staging: {matching[-1]}")
                with open(fpath, 'rb') as f:
                    result[key] = f.read()
        if not result:
            raise FileNotFoundError("No se encontraron archivos de staging válidos")
        return result

    # --- Parsing robusto ---
    def _parse_excel(self, excel_bytes: bytes, label: str) -> pd.DataFrame:
        """
        Parsea un Excel de la NY Fed con detección automática del formato.
        Prueba múltiples estrategias de lectura para manejar las diferencias
        entre el formato antiguo y el nuevo.
        """
        self.logger.info(f"Procesando Excel {label}...")

        # Estrategia: leer con header=None y buscar la fila de headers manualmente
        # Esto es más robusto que detectar con openpyxl por separado
        df_raw = pd.read_excel(
            io.BytesIO(excel_bytes),
            sheet_name='volume_haircut_concentration',
            header=None,
            engine='openpyxl'
        )

        # Buscar la fila donde aparece "date" en la primera columna
        header_row = None
        for idx, row in df_raw.iterrows():
            first_val = str(row.iloc[0]).lower().strip() if pd.notna(row.iloc[0]) else ''
            if first_val == 'date':
                header_row = idx
                break

        if header_row is None:
            self.logger.error(f"No se encontraron headers en {label}")
            return pd.DataFrame()

        self.logger.info(f"  Headers encontrados en fila {header_row}")

        # Usar esa fila como headers y todo lo de abajo como datos
        df = df_raw.iloc[header_row + 1:].copy()
        df.columns = list(df_raw.iloc[header_row])

        # Resetear índice
        df.reset_index(drop=True, inplace=True)

        # Eliminar filas completamente vacías
        df.dropna(how='all', inplace=True)

        # Renombrar columnas al formato estándar
        # (manejar posibles diferencias de nombres entre versiones)
        col_list = list(df.columns)
        rename_map = {}
        for i, col in enumerate(col_list):
            if i < len(self.EXPECTED_COLUMNS) and col != self.EXPECTED_COLUMNS[i]:
                rename_map[col] = self.EXPECTED_COLUMNS[i]
        if rename_map:
            df.rename(columns=rename_map, inplace=True)

        # Asegurar que no hay columnas duplicadas
        if df.columns.duplicated().any():
            self.logger.warning(f"  Columnas duplicadas detectadas, eliminando duplicados")
            df = df.loc[:, ~df.columns.duplicated(keep='first')]

        # Convertir fecha (formato YYYYMMDD como string o int)
        df['date'] = pd.to_numeric(df['date'], errors='coerce')
        df['date'] = pd.to_datetime(df['date'].astype('Int64').astype(str), format='%Y%m%d', errors='coerce')
        df.dropna(subset=['date'], inplace=True)

        # Limpiar columnas numéricas de forma segura
        numeric_cols = [
            'collateral_value', 'share_of_total', 'top_3_concentration',
            'p10', 'median', 'p90', 'fedwire', 'num_obs', 'margin_stdev'
        ]
        for col in numeric_cols:
            if col in df.columns:
                # Verificar que es una Series, no un DataFrame (columnas duplicadas)
                if isinstance(df[col], pd.DataFrame):
                    self.logger.warning(f"  Columna '{col}' duplicada, usando primera")
                    df[col] = df[col].iloc[:, 0]
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # Filtrar filas válidas
        df = df.dropna(subset=['group_name'])
        df['collateral_value'] = pd.to_numeric(df.get('collateral_value', 0), errors='coerce')
        df = df[df['collateral_value'] > 0]

        self.logger.info(f"  → {len(df)} registros válidos en {label}")
        return df

    def transform(self, raw_data: dict) -> list[dict]:
        all_dfs = []
        for key in ['pre', 'post']:
            if key in raw_data:
                df = self._parse_excel(raw_data[key], f"datos {key}-Nov2025")
                if not df.empty:
                    all_dfs.append(df)

        if not all_dfs:
            return []

        df_combined = pd.concat(all_dfs, ignore_index=True)
        df_combined.sort_values('date', inplace=True)
        df_combined.drop_duplicates(subset=['date', 'group_name'], keep='last', inplace=True)

        clean = []
        for _, row in df_combined.iterrows():
            clean.append({
                'date': row['date'].date(),
                'group_id': int(row['group_id']) if pd.notna(row.get('group_id')) else None,
                'group_name': str(row['group_name']).strip(),
                'collateral_value': float(row['collateral_value']),
                'share_of_total': float(row['share_of_total']) if pd.notna(row.get('share_of_total')) else None,
                'top_3_concentration': float(row['top_3_concentration']) if pd.notna(row.get('top_3_concentration')) else None,
                'margin_p10': float(row['p10']) if pd.notna(row.get('p10')) else None,
                'margin_median': float(row['median']) if pd.notna(row.get('median')) else None,
                'margin_p90': float(row['p90']) if pd.notna(row.get('p90')) else None,
                'fedwire_eligible': float(row['fedwire']) if pd.notna(row.get('fedwire')) else None,
                'num_observations': int(row['num_obs']) if pd.notna(row.get('num_obs')) else None,
                'margin_stdev': float(row['margin_stdev']) if pd.notna(row.get('margin_stdev')) else None,
            })

        self.logger.info(f"Total combinado: {len(clean)} registros")
        return clean

    def load(self, clean_data: list[dict]) -> int:
        batch_size = 500
        loaded = 0
        with get_session() as session:
            for i in range(0, len(clean_data), batch_size):
                batch = clean_data[i:i + batch_size]
                for row in batch:
                    stmt = sqlite_upsert(RepoOperation).values(**row)
                    stmt = stmt.on_conflict_do_nothing(index_elements=['date', 'group_name'])
                    session.execute(stmt)
                session.commit()
                loaded += len(batch)
                if loaded % 5000 == 0:
                    self.logger.info(f"Carga: {loaded}/{len(clean_data)} registros")
        return len(clean_data)
        