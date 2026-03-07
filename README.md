# Economy Monitor

Sistema modular de recopilación, almacenamiento y visualización de datos económicos y financieros.

## Stack

- **Dashboard:** Dash + Plotly (localhost:8050)
- **Base de datos:** SQLite + SQLAlchemy + Alembic
- **Scheduler:** APScheduler
- **Scraping:** BeautifulSoup4 / Selenium

## Instalación rápida

```bash
cd economy_monitor
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

pip install -r requirements.txt
```

## Uso

### 1. Descargar datos (primera vez)
```bash
python run_pipeline.py treasury
```

### 2. Abrir el dashboard
```bash
python run_dashboard.py
# → Abrir http://127.0.0.1:8050 en el navegador
```

### 3. Activar descargas automáticas (opcional)
```bash
python run_scheduler.py
```

## Pipelines disponibles

| Pipeline | Fuente | Estado |
|---|---|---|
| `treasury` | FiscalData API (Tesoro USA) | ✅ Implementado |
| `nfci` | FRED API (Fed Chicago) | 🔲 Pendiente |
| `indices` | Yahoo Finance | 🔲 Pendiente |
| `repo` | NY Fed API | 🔲 Pendiente |
| `ecb` | BCE (API + scraping) | 🔲 Pendiente |

## Estructura del proyecto

```
economy_monitor/
├── run_dashboard.py       # Arranca el dashboard web
├── run_scheduler.py       # Arranca descargas automáticas
├── run_pipeline.py        # Ejecuta un pipeline manualmente
├── config/                # Configuración central
├── db/                    # Base de datos, modelos, migraciones
├── pipelines/             # Pipelines ETL (uno por fuente)
├── scheduler/             # Jobs programados
├── dashboard/             # App Dash (páginas, componentes)
├── utils/                 # Logger, rate limiter, helpers
├── data/                  # SQLite DB (se crea automáticamente)
└── logs/                  # Archivos de log rotados
```
