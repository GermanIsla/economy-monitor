# config/settings.py
# Configuración central del proyecto Economy Monitor

import os

# --- Rutas ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(BASE_DIR, "logs")
DB_PATH = os.path.join(DATA_DIR, "economy_monitor.db")

# --- Base de datos ---
DB_URL = f"sqlite:///{DB_PATH}"
DB_ECHO = False  # True para ver las queries SQL en consola (depuración)

# Crear directorios si no existen
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# --- Dashboard ---
DASH_HOST = "127.0.0.1"
DASH_PORT = 8050
DASH_DEBUG = True

# --- Rate limiting global (segundos entre peticiones) ---
DEFAULT_RATE_LIMIT = 1.0

# --- Configuración por fuente de datos ---
SOURCES = {
    "treasury": {
        "base_url": "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query",
        "rate_limit": 0.5,
        "schedule": {"trigger": "cron", "hour": 8, "minute": 0},
    },
    "nfci": {
        "base_url": "https://api.stlouisfed.org/fred/series/observations",
        "rate_limit": 1.0,
        "schedule": {"trigger": "cron", "day_of_week": "fri", "hour": 12},
    },
    "indices": {
        "rate_limit": 2.0,
        "schedule": {"trigger": "interval", "hours": 6},
    },
    "repo": {
        "base_url": "https://markets.newyorkfed.org/api/rp/results/search",
        "rate_limit": 1.0,
        "schedule": {"trigger": "cron", "hour": 10, "minute": 0},
    },
    "ecb": {
        "base_url": "https://data-api.ecb.europa.eu/service/data/MMSR/",
        "rate_limit": 3.0,
        "schedule": {"trigger": "cron", "hour": 9, "minute": 0}, # Se publica por la mañana
    },
    "fred": {
        "base_url": "https://api.stlouisfed.org/fred/series/observations",
        "api_key": os.getenv("FRED_API_KEY", ""),
        "rate_limit": 0.5,  # segundos entre peticiones
    },
    # Añadir nuevas fuentes aquí siguiendo el mismo patrón
}
