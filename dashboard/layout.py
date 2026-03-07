# dashboard/layout.py
# Layout principal: sidebar de navegación + área de contenido dinámico

import dash
from dash import html, dcc
import dash_bootstrap_components as dbc


def create_layout():
    """Layout raíz de la aplicación."""
    return dbc.Container([
        # Store para datos compartidos entre páginas
        dcc.Store(id='global-store'),

        dbc.Row([
            # --- SIDEBAR ---
            dbc.Col([
                html.Div([
                    # Logo / Título
                    html.H4(
                        "Economy Monitor",
                        className="text-center my-3 fw-bold text-primary"
                    ),
                    html.P(
                        "Panel de Control Económico",
                        className="text-center text-muted small mb-4"
                    ),
                    html.Hr(className="border-secondary"),

                    # Navegación
                    dbc.Nav([
                        dbc.NavLink([
                            html.I(className="bi bi-speedometer2 me-2"),
                            "Resumen General"
                        ], href="/", active="exact"),

                        dbc.NavLink([
                            html.I(className="bi bi-bank me-2"),
                            "Tesoro USA"
                        ], href="/treasury", active="exact"),

                        dbc.NavLink([
                            html.I(className="bi bi-graph-up me-2"),
                            "Índices Globales"
                        ], href="/indices", active="exact"),

                        dbc.NavLink([
                            html.I(className="bi bi-activity me-2"),
                            "NFCI"
                        ], href="/nfci", active="exact"),

                        dbc.NavLink([
                            html.I(className="bi bi-arrow-left-right me-2"),
                            "Repo"
                        ], href="/repo", active="exact"),

                        html.Hr(className="border-secondary"),

                        dbc.NavLink([
                            html.I(className="bi bi-gear me-2"),
                            "Estado del Sistema"
                        ], href="/status", active="exact"),

                    ], vertical=True, pills=True),
                ], className="position-sticky top-0")
            ], width=2, className="bg-dark min-vh-100 p-3 border-end border-secondary"),

            # --- CONTENIDO PRINCIPAL ---
            dbc.Col([
                dash.page_container
            ], width=10, className="p-4"),

        ], className="g-0"),
    ], fluid=True, className="p-0")
