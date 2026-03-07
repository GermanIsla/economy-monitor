# dashboard/pages/overview.py
# Página de resumen general — equivalente al cuadro resumen de la versión terminal

import dash
from dash import html, dcc, callback, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import select, func
from db.engine import get_session
from db.models.treasury import TreasuryAuction
from db.models.nfci import NFCIReading
from db.models.pipeline_metadata import PipelineRun
from dashboard.components.cards import kpi_card

dash.register_page(
    __name__,
    path="/",
    name="Resumen General",
    title="Economy Monitor | Resumen"
)

layout = dbc.Container([
    html.H2("Resumen General", className="mb-1"),
    html.P(
        "Vista rápida del estado de los principales indicadores económicos.",
        className="text-muted mb-4"
    ),
    html.Hr(),

    # Auto-refresh cada 5 minutos
    dcc.Interval(id='overview-refresh', interval=5 * 60 * 1000, n_intervals=0),

    # Fila de KPI cards
    html.Div(id="overview-kpi-cards", className="mb-4"),

    # Gráfico principal
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Emisión de Deuda del Tesoro (últimos 6 meses)",
                             className="card-title"),
                    dcc.Graph(id="overview-treasury-chart")
                ])
            ])
        ], width=12),
    ], className="mb-4"),

    # Estado de pipelines
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Estado de las Fuentes de Datos", className="card-title"),
                    html.Div(id="overview-pipeline-status")
                ])
            ])
        ], width=12),
    ]),

], fluid=True)


@callback(
    Output("overview-kpi-cards", "children"),
    Output("overview-treasury-chart", "figure"),
    Output("overview-pipeline-status", "children"),
    Input("overview-refresh", "n_intervals"),
)
def update_overview(n):
    """Actualiza todos los componentes de la página de resumen."""

    from utils.helpers import format_amount

    # --- KPI: Emisión de deuda últimos 14 días ---
    bills_total = 0
    notes_total = 0
    try:
        fecha_limite = datetime.now().date() - timedelta(days=14)
        with get_session() as session:
            stmt = select(TreasuryAuction).where(
                TreasuryAuction.issue_date >= fecha_limite
            )
            results = session.execute(stmt).scalars().all()

        for r in results:
            if r.security_type == 'Bill':
                bills_total += r.total_accepted
            elif r.security_type == 'Note':
                notes_total += r.total_accepted
    except Exception:
        pass

    # --- KPI: Último valor NFCI ---
    nfci_value = "Sin datos"
    nfci_delta = None
    nfci_delta_color = "secondary"
    try:
        with get_session() as session:
            stmt = (
                select(NFCIReading)
                .where(NFCIReading.indicator_name == 'NFCI')
                .order_by(NFCIReading.date.desc())
                .limit(2)
            )
            nfci_rows = session.execute(stmt).scalars().all()

        if nfci_rows:
            nfci_value = f"{nfci_rows[0].value:.3f}"
            if len(nfci_rows) >= 2:
                change = nfci_rows[0].value - nfci_rows[1].value
                nfci_delta = f"{change:+.3f}"
                nfci_delta_color = "danger" if change > 0 else "success"
    except Exception:
        pass

    kpi_row = dbc.Row([
        dbc.Col(kpi_card(
            "Bills (14 días)", format_amount(bills_total),
            icon="bi-cash-stack"
        ), width=3),
        dbc.Col(kpi_card(
            "Notes (14 días)", format_amount(notes_total),
            icon="bi-file-earmark-text"
        ), width=3),
        dbc.Col(kpi_card(
            "NFCI", nfci_value,
            delta=nfci_delta,
            delta_color=nfci_delta_color,
            icon="bi-activity"
        ), width=3),
        dbc.Col(kpi_card(
            "Repo Vol.", "Pendiente",
            icon="bi-arrow-left-right"
        ), width=3),
    ])

    # --- Gráfico de emisión reciente ---
    fig = go.Figure()
    try:
        fecha_6m = datetime.now().date() - timedelta(days=180)
        with get_session() as session:
            stmt = select(TreasuryAuction).where(
                TreasuryAuction.issue_date >= fecha_6m
            ).order_by(TreasuryAuction.issue_date)
            results = session.execute(stmt).scalars().all()

        if results:
            df = pd.DataFrame([{
                'issue_date': r.issue_date,
                'security_type': r.security_type,
                'total_accepted': r.total_accepted,
            } for r in results])

            # Agrupar por semana y tipo
            df['issue_date'] = pd.to_datetime(df['issue_date'])
            df_weekly = df.groupby([
                pd.Grouper(key='issue_date', freq='W'),
                'security_type'
            ])['total_accepted'].sum().reset_index()

            for sec_type in ['Bill', 'Note', 'Bond']:
                mask = df_weekly['security_type'] == sec_type
                if mask.any():
                    fig.add_trace(go.Bar(
                        x=df_weekly.loc[mask, 'issue_date'],
                        y=df_weekly.loc[mask, 'total_accepted'] / 1e9,
                        name=sec_type,
                    ))

            fig.update_layout(barmode='stack')
    except Exception:
        pass

    fig.update_layout(
        template='plotly_dark',
        title_x=0.5,
        yaxis_title="Miles de Millones USD",
        xaxis_title="Semana",
        legend={'orientation': 'h', 'y': -0.15},
        margin={'l': 60, 'r': 30, 't': 40, 'b': 60},
    )

    # --- Estado de pipelines ---
    pipeline_badges = []
    try:
        with get_session() as session:
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
            latest = session.execute(stmt).scalars().all()

        from utils.helpers import time_ago
        for run in latest:
            color = {
                "success": "success", "error": "danger", "running": "warning"
            }.get(run.status, "secondary")

            pipeline_badges.append(
                dbc.Badge([
                    html.Span(run.pipeline_name, className="me-1"),
                    html.Small(f"({time_ago(run.finished_at)})")
                ], color=color, className="me-2 p-2", pill=True)
            )
    except Exception:
        pipeline_badges = [html.P("Sin datos de pipelines", className="text-muted")]

    if not pipeline_badges:
        pipeline_badges = [html.P(
            "No se han ejecutado pipelines todavía. Ejecuta: python run_pipeline.py treasury",
            className="text-muted"
        )]

    return kpi_row, fig, html.Div(pipeline_badges)
