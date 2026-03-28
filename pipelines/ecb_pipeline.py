# pipelines/ecb_pipeline.py

import pandas as pd
import io
import requests
from datetime import date
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
from pipelines.base import BasePipeline
from db.engine import get_session
from db.models.ecb import ECBMarketIndicator
from utils.rate_limiter import RateLimiter
from config.settings import SOURCES

# Mapeo de tus IDs internos a las "keys" del BCE que me pasaste
ECB_SERIES = {
    # --- SECURED (Wholesale - S1ZV) ---
    'mmsr_sec_whls_bo_ov': 'B.U2._X._Z.S1ZV._Z.T.BO.TT._X.MA._Z._Z.EUR._Z',
    # --- SECURED Wholesale LENDING overnight (volumen, para comparar con borrowing) ---
    'mmsr_sec_whls_le_ov':     'B.U2._X._Z.S1ZV._Z.T.LE.TT._X.MA._Z._Z.EUR._Z',

    # --- SECURED Wholesale por país (overnight lending) ---
    # Mismo colateral que S1ZV total, pero desglosado geográficamente
    # Permite ver qué mercados nacionales dominan el flujo de repos
    'mmsr_sec_whls_le_ov_de': 'B.U2._X.DE.S1ZV._Z.T.LE.TT._X.MA._Z._Z.EUR._Z',
    'mmsr_sec_whls_le_ov_fr': 'B.U2._X.FR.S1ZV._Z.T.LE.TT._X.MA._Z._Z.EUR._Z',
    'mmsr_sec_whls_le_ov_it': 'B.U2._X.IT.S1ZV._Z.T.LE.TT._X.MA._Z._Z.EUR._Z',
    'mmsr_sec_whls_le_ov_es': 'B.U2._X.ES.S1ZV._Z.T.LE.TT._X.MA._Z._Z.EUR._Z',

    # --- SECURED Wholesale por país (overnight borrowing) ---
    'mmsr_sec_whls_bo_ov_de': 'B.U2._X.DE.S1ZV._Z.T.BO.TT._X.MA._Z._Z.EUR._Z',
    'mmsr_sec_whls_bo_ov_fr': 'B.U2._X.FR.S1ZV._Z.T.BO.TT._X.MA._Z._Z.EUR._Z',
    'mmsr_sec_whls_bo_ov_it': 'B.U2._X.IT.S1ZV._Z.T.BO.TT._X.MA._Z._Z.EUR._Z',
    'mmsr_sec_whls_bo_ov_es': 'B.U2._X.ES.S1ZV._Z.T.BO.TT._X.MA._Z._Z.EUR._Z',

    # --- CCP — Cámaras de Compensación (S12U, overnight) ---
    # ~70% del mercado de repos europeo pasa por CCPs (LCH, Eurex)
    # Si CCP sube mientras interbancario bilateral baja → preferencia por neteo y seguridad
    #'mmsr_sec_ccp_le_ov': 'B.U2._X._Z.S12U._Z.T.LE.TT._X.MA._Z._Z.EUR._Z',
    #'mmsr_sec_ccp_bo_ov': 'B.U2._X._Z.S12U._Z.T.BO.TT._X.MA._Z._Z.EUR._Z',
    
    # --- UNSECURED Wholesale (S1ZV) ---
    'mmsr_unsec_whls_bo_ov':  'B.U2._X._Z.S1ZV._Z.U.BO.TT._X.MA._Z._Z.EUR._Z',
    'mmsr_unsec_whls_bo_tn':  'B.U2._X._Z.S1ZV._Z.U.BO.TT._X.KT._Z._Z.EUR._Z',
    'mmsr_unsec_whls_bo_sn':  'B.U2._X._Z.S1ZV._Z.U.BO.TT._X.KS._Z._Z.EUR._Z',
    'mmsr_unsec_whls_bo_1w':  'B.U2._X._Z.S1ZV._Z.U.BO.TT._X.TA._Z._Z.EUR._Z',
    'mmsr_unsec_whls_bo_1m':  'B.U2._X._Z.S1ZV._Z.U.BO.TT._X.TC._Z._Z.EUR._Z',
    'mmsr_unsec_whls_bo_3m':  'B.U2._X._Z.S1ZV._Z.U.BO.TT._X.TE._Z._Z.EUR._Z',
    'mmsr_unsec_whls_bo_12m': 'B.U2._X._Z.S1ZV._Z.U.BO.TT._X.TH._Z._Z.EUR._Z',

    # --- UNSECURED Interbank (S122) ---
    'mmsr_unsec_intb_bo_tn':  'B.U2._X._Z.S122._Z.U.BO.TT._X.KT._Z._Z.EUR._Z',
    'mmsr_unsec_intb_bo_sn':  'B.U2._X._Z.S122._Z.U.BO.TT._X.KS._Z._Z.EUR._Z',
    'mmsr_unsec_intb_bo_1w':  'B.U2._X._Z.S122._Z.U.BO.TT._X.TA._Z._Z.EUR._Z',
    'mmsr_unsec_intb_bo_1m':  'B.U2._X._Z.S122._Z.U.BO.TT._X.TC._Z._Z.EUR._Z',
    'mmsr_unsec_intb_bo_3m':  'B.U2._X._Z.S122._Z.U.BO.TT._X.TE._Z._Z.EUR._Z',
    'mmsr_unsec_intb_bo_12m': 'B.U2._X._Z.S122._Z.U.BO.TT._X.TH._Z._Z.EUR._Z',
    'mmsr_unsec_intb_bo_ov':  'B.U2._X._Z.S122._Z.U.BO.TT._X.MA._Z._Z.EUR._Z',
    'mmsr_unsec_intb_le_ov':  'B.U2._X._Z.S122._Z.U.LE.TT._X.MA._Z._Z.EUR._Z',

    # --- WEIGHTED AVERAGE RATES (WR) Secured overnight ---
    # Usamos estos para detectar escasez de colateral:
    # Si tipo WR < DFR → bancos prestan dinero casi gratis por conseguir el bono
    'mmsr_sec_whls_le_ov_wr':  'B.U2._X._Z.S1ZV._Z.T.LE.WR._X.MA._Z._Z.EUR._Z',
    'mmsr_sec_whls_bo_ov_wr':  'B.U2._X._Z.S1ZV._Z.T.BO.WR._X.MA._Z._Z.EUR._Z',
    'mmsr_unsec_intb_le_ov_wr':'B.U2._X._Z.S122._Z.U.LE.WR._X.MA._Z._Z.EUR._Z',
}

# Series de tipos de política monetaria (dataset FM, diferente base URL)
ECB_POLICY_RATES = {
    'ecb_dfr': 'D.U2.EUR.4F.KR.DFR.LEV',   # Deposit Facility Rate
    'ecb_mro': 'B.U2.EUR.4F.KR.MRR_FR.LEV', # Main Refinancing Operations Rate
}


ECB_EST_RATES = {
    'ecb_estr': 'B.EU000A2X2A25.WT',  # Euro Short-Term Rate
}
# Lookup unificado para transform()
ALL_ECB_SERIES = {**ECB_SERIES, **ECB_POLICY_RATES, **ECB_EST_RATES}

FM_BASE_URL = "https://data-api.ecb.europa.eu/service/data/FM/"
EST_BASE_URL = "https://data-api.ecb.europa.eu/service/data/EST/"

class ECBPipeline(BasePipeline):
    def __init__(self):
        super().__init__()
        config = SOURCES['ecb']
        self.base_url = config['base_url']
        self.limiter = RateLimiter(min_interval=config['rate_limit'])

    min_interval_hours = 600.0  # Mensual (~25 días)

    @property
    def name(self) -> str:
        return "ecb"

    def extract(self, since_date: date = None) -> dict[str, str]:
        """Descarga datos MMSR (liquidez) y FM (tipos oficiales BCE)."""
        all_raw_csv = {}
        params_base = {'format': 'csvdata'}
        if since_date:
            params_base['startPeriod'] = since_date.isoformat()

        # --- Series MMSR (volumen + tipos de mercado) ---
        for internal_id, ecb_key in ECB_SERIES.items():
            self.logger.info(f"Extrayendo MMSR: {internal_id}")
            self.limiter.wait()
            url = f"{self.base_url}{ecb_key}"
            try:
                resp = requests.get(url, params=params_base, timeout=30)
                resp.raise_for_status()
                all_raw_csv[internal_id] = resp.text
            except Exception as e:
                self.logger.error(f"Error descargando {internal_id}: {e}")

        # --- Series FM (DFR, MRO — tipos oficiales del BCE) ---
        for internal_id, fm_key in ECB_POLICY_RATES.items():
            self.logger.info(f"Extrayendo FM (tipos BCE): {internal_id}")
            self.limiter.wait()
            url = f"{FM_BASE_URL}{fm_key}"
            try:
                resp = requests.get(url, params=params_base, timeout=30)
                resp.raise_for_status()
                all_raw_csv[internal_id] = resp.text
            except Exception as e:
                self.logger.error(f"Error descargando {internal_id}: {e}")
        # --- Series EST (€STR) ---
        for internal_id, est_key in ECB_EST_RATES.items():
            self.logger.info(f"Extrayendo EST (€STR): {internal_id}")
            self.limiter.wait()
            url = f"{EST_BASE_URL}{est_key}"
            try:
                resp = requests.get(url, params=params_base, timeout=30)
                resp.raise_for_status()
                all_raw_csv[internal_id] = resp.text
            except Exception as e:
                self.logger.error(f"Error descargando {internal_id}: {e}")

        return all_raw_csv

    def transform(self, raw_data: dict[str, str]) -> list[dict]:
        """Transforma los CSVs del BCE en diccionarios limpios para la DB."""
        clean_records = []
        
        for internal_id, csv_content in raw_data.items():
            if not csv_content or "TIME_PERIOD" not in csv_content:
                self.logger.warning(f"CSV vacío o mal formado para {internal_id}")
                continue
            
            # Leemos el CSV directamente a un DataFrame
            df = pd.read_csv(io.StringIO(csv_content))
            
            # La API del BCE en modo 'csvdata' usa estas columnas estándar:
            # TIME_PERIOD (fecha) y OBS_VALUE (el dato)
            for _, row in df.iterrows():
                try:
                    # El BCE a veces usa NaN para valores no disponibles
                    if pd.isna(row['OBS_VALUE']): continue
                    clean_records.append({
                        'date': pd.to_datetime(row['TIME_PERIOD']).date(),
                        'series_id': internal_id,
                        'value': float(row['OBS_VALUE']),
                        'description': ALL_ECB_SERIES.get(internal_id, internal_id)
                    })
                except (ValueError, KeyError):
                    continue
                    
        return clean_records

    def load(self, clean_data: list[dict]) -> int:
        """Carga los datos usando UPSERT para evitar duplicados."""
        if not clean_data: return 0
        
        with get_session() as session:
            for row in clean_data:
                stmt = sqlite_upsert(ECBMarketIndicator).values(**row)
                # Si hay conflicto en (date, series_id), no hacemos nada (mantenemos el existente)
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=['date', 'series_id']
                )
                session.execute(stmt)
            session.commit()
            
        return len(clean_data)