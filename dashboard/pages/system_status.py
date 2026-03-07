# dashboard/pages/system_status.py
# Página de monitorización del estado de todos los pipelines

import dash
from dash import html, dcc, callback, Input, Output
import dash_bootstrap_components as dbc
from datetime import datetime
from sqlalchemy import select, func
from db.engine import get_session
from db.models.pipeline_metadata import PipelineRun
from utils.helpers import time_ago

dash.register_page(
    __name__,
    path="/status",
    name="Estado del Sistema",
    title="Economy Monitor | Estado"
)

layout = dbc.Container([
    html.H2("Estado del Sistema", className="mb-1"),
    html.P(
        "Monitorización de pipelines, última actualización y errores.",
        className="text-muted mb-4"
    ),
    html.Hr(),

    # Auto-refresh cada 30 segundos
    dcc.Interval(id='status-refresh', interval=30 * 1000, n_intervals=0),

    # Tarjetas de estado por pipeline
    html.H4("Estado Actual de los Pipelines", className="mb-3"),
    html.Div(id="status-pipeline-cards", className="mb-4"),

    # Tabla de ejecuciones recientes
    html.H4("Últimas 20 Ejecuciones", className="mb-3"),
    html.Div(id="status-recent-runs"),

], fluid=True)


@callback(
    Output("status-pipeline-cards", "children"),
    Output("status-recent-runs", "children"),
    Input("status-refresh", "n_intervals"),
)
def update_status(n):
    """Consulta el estado de cada pipeline y genera la vista."""

    try:
        with get_session() as session:
            # Última ejecución de cada pipeline
            subquery = (
                select(
                    PipelineRun.pipeline_name,
                    func.max(PipelineRun.id).label('last_id')
                )
                .group_by(PipelineRun.pipeline_name)
                .subquery()
            )
            stmt = select(PipelineRun).join(
                subquery, PipelineRun.id == subquery.c.last_id
            )
            latest_runs = session.execute(stmt).scalars().all()

            # Últimas 20 ejecuciones globales
            stmt_recent = (
                select(PipelineRun)
                .order_by(PipelineRun.started_at.desc())
                .limit(20)
            )
            recent_runs = session.execute(stmt_recent).scalars().all()
    except Exception:
        return (
            html.P("Error al consultar la base de datos.", className="text-danger"),
            html.P("Sin datos disponibles.")
        )

    # --- Tarjetas de estado ---
    if not latest_runs:
        cards = dbc.Alert(
            "No se han ejecutado pipelines todavía. "
            "Ejecuta: python run_pipeline.py treasury",
            color="info"
        )
    else:
        card_list = []
        for run in latest_runs:
            if run.status == "success":
                color, icon = "success", "bi-check-circle-fill"
            elif run.status == "error":
                color, icon = "danger", "bi-x-circle-fill"
            else:
                color, icon = "warning", "bi-hourglass-split"

            card_list.append(dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className=f"bi {icon} text-{color} fs-4"),
                            html.Span(run.pipeline_name, className="ms-2 fw-bold"),
                        ]),
                        html.P(f"Estado: {run.status}", className="mb-1 mt-2"),
                        html.P(
                            f"Registros: {run.records_processed}",
                            className="mb-1 small text-muted"
                        ),
                        html.P(
                            time_ago(run.finished_at),
                            className="mb-0 small text-muted"
                        ),
                        html.P(
                            run.error_message[:100] if run.error_message else "",
                            className="text-danger small mt-1 mb-0"
                        ) if run.error_message else None,
                    ])
                ], className=f"border-{color} h-100")
            ], width=3, className="mb-3"))

        cards = dbc.Row(card_list)

    # --- Tabla de ejecuciones recientes ---
    if not recent_runs:
        table = html.P("Sin ejecuciones registradas.", className="text-muted")
    else:
        table_rows = []
        for run in recent_runs:
            badge_color = {
                "success": "success", "error": "danger", "running": "warning"
            }.get(run.status, "secondary")

            table_rows.append(html.Tr([
                html.Td(run.pipeline_name),
                html.Td(dbc.Badge(run.status, color=badge_color, pill=True)),
                html.Td(str(run.records_processed)),
                html.Td(
                    run.started_at.strftime("%Y-%m-%d %H:%M")
                    if run.started_at else ""
                ),
                html.Td(
                    run.finished_at.strftime("%H:%M:%S")
                    if run.finished_at else "—"
                ),
                html.Td(
                    run.error_message[:80] if run.error_message else "",
                    className="text-danger small"
                ),
            ]))

        table = dbc.Table([
            html.Thead(html.Tr([
                html.Th("Pipeline"),
                html.Th("Estado"),
                html.Th("Registros"),
                html.Th("Inicio"),
                html.Th("Fin"),
                html.Th("Error"),
            ])),
            html.Tbody(table_rows)
        ], bordered=True, hover=True, responsive=True, striped=True)

    return cards, table
