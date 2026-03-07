# dashboard/pages/indices.py
# Página de comparativa de índices globales — PENDIENTE DE IMPLEMENTAR
# Se activará cuando se implemente IndicesPipeline

import dash
from dash import html
import dash_bootstrap_components as dbc

dash.register_page(
    __name__,
    path="/indices",
    name="Índices Globales",
    title="Economy Monitor | Índices"
)

layout = dbc.Container([
    html.H2("Comparativa de Índices Globales", className="mb-1"),
    html.P("Fuerza relativa entre mercados mundiales.", className="text-muted mb-4"),
    html.Hr(),
    dbc.Alert([
        html.I(className="bi bi-info-circle me-2"),
        "Esta página se activará cuando se implemente el pipeline de índices. ",
        html.Code("python run_pipeline.py indices"),
    ], color="info", className="mt-4"),
], fluid=True)
