# dashboard/app.py
# Inicialización de la aplicación Dash

import dash
import dash_bootstrap_components as dbc
from dashboard.layout import create_layout

app = dash.Dash(
    __name__,
    use_pages=True,
    pages_folder="pages",
    external_stylesheets=[
        dbc.themes.DARKLY,
        dbc.icons.BOOTSTRAP,  # Iconos Bootstrap
    ],
    suppress_callback_exceptions=True,
    title="Economy Monitor",
    update_title="Cargando...",
)

app.layout = create_layout()

# Exponer el server Flask para run_dashboard.py
server = app.server
