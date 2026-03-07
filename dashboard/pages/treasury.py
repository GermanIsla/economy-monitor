# dashboard/pages/treasury.py
# Página de análisis de deuda del Tesoro de EE.UU.
# Equivalente a treasury_organicer.py y treasury_organicer_console.py

import dash
from dash import html, dcc, callback, Input, Output
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import select
from db.engine import get_session
from db.models.treasury import TreasuryAuction

dash.register_page(
    __name__,
    path="/treasury",
    name="Tesoro USA",
    title="Economy Monitor | Tesoro USA"
)

layout = dbc.Container([
    html.H2("Análisis de Deuda del Tesoro de EE.UU.", className="mb-1"),
    html.P(
        "Evolución de la deuda en circulación y muro de vencimientos.",
        className="text-muted mb-4"
    ),
    html.Hr(),

    # --- Filtros ---
    dbc.Row([
        dbc.Col([
            html.Label("Tipo de deuda:", className="fw-bold"),
            dcc.Dropdown(
                id="treasury-type-filter",
                options=[
                    {"label": "Bills (Letras)", "value": "Bill"},
                    {"label": "Notes (Bonos medio plazo)", "value": "Note"},
                    {"label": "Bonds (Bonos largo plazo)", "value": "Bond"},
                ],
                value=["Bill", "Note", "Bond"],
                multi=True,
                clearable=False
            ),
        ], width=4),
        dbc.Col([
            html.Label("Periodo de circulación:", className="fw-bold"),
            dcc.Dropdown(
                id="treasury-period-filter",
                options=[
                    {"label": "1 año", "value": 365},
                    {"label": "2 años", "value": 730},
                    {"label": "5 años", "value": 1825},
                    {"label": "Todo el histórico", "value": 0},
                ],
                value=730,
                clearable=False
            ),
        ], width=3),
    ], className="mb-4"),

    # --- Gráfico 1: Deuda en circulación ---
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    dcc.Graph(id="treasury-circulation-chart")
                ])
            ])
        ], width=12),
    ], className="mb-4"),

    # --- Gráfico 2: Muro de vencimientos ---
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Muro de Vencimientos (próximos 2 años)",
                             className="card-title"),
                    dcc.Graph(id="treasury-maturity-wall-chart")
                ])
            ])
        ], width=12),
    ]),

], fluid=True)


@callback(
    Output("treasury-circulation-chart", "figure"),
    Output("treasury-maturity-wall-chart", "figure"),
    Input("treasury-type-filter", "value"),
    Input("treasury-period-filter", "value"),
)
def update_treasury_charts(types, period_days):
    """Lee de SQLite y genera los gráficos de deuda."""

    # Asegurar que types sea una lista
    if isinstance(types, str):
        types = [types]
    if not types:
        types = ['Bill', 'Note', 'Bond']

    # --- Leer datos de la DB ---
    with get_session() as session:
        stmt = select(TreasuryAuction).where(
            TreasuryAuction.security_type.in_(types)
        ).order_by(TreasuryAuction.issue_date)
        results = session.execute(stmt).scalars().all()

    if not results:
        empty_fig = go.Figure()
        empty_fig.update_layout(
            template='plotly_dark',
            annotations=[{
                'text': 'Sin datos. Ejecuta: python run_pipeline.py treasury',
                'xref': 'paper', 'yref': 'paper',
                'x': 0.5, 'y': 0.5, 'showarrow': False,
                'font': {'size': 16, 'color': 'gray'}
            }]
        )
        return empty_fig, empty_fig

    df = pd.DataFrame([{
        'issue_date': r.issue_date,
        'maturity_date': r.maturity_date,
        'security_type': r.security_type,
        'total_accepted': r.total_accepted,
    } for r in results])

    df['issue_date'] = pd.to_datetime(df['issue_date'])
    df['maturity_date'] = pd.to_datetime(df['maturity_date'])
    last_issue_date = df['issue_date'].max()

    # ==========================================================
    # GRÁFICO 1: Deuda en circulación por tipo
    # ==========================================================
    # Crear eventos: emisiones (+) y vencimientos (-)
    emisiones = df[['issue_date', 'security_type', 'total_accepted']].rename(
        columns={'issue_date': 'date', 'total_accepted': 'amount'}
    )
    vencimientos = df[['maturity_date', 'security_type', 'total_accepted']].rename(
        columns={'maturity_date': 'date', 'total_accepted': 'amount'}
    )
    vencimientos['amount'] = -vencimientos['amount']

    eventos = pd.concat([emisiones, vencimientos])
    flujo = eventos.pivot_table(
        index='date', columns='security_type', values='amount', aggfunc='sum'
    ).fillna(0)
    circulante = flujo.cumsum()

    # Filtrar por periodo
    circulante = circulante[circulante.index <= last_issue_date]
    if period_days > 0:
        fecha_inicio = last_issue_date - pd.DateOffset(days=period_days)
        circulante = circulante[circulante.index >= fecha_inicio]

    # Convertir a billones (trillions en inglés)
    circulante_T = (circulante / 1e12).reset_index()
    df_long = circulante_T.melt(
        id_vars='date',
        var_name='Tipo de Deuda',
        value_name='Total en Circulación'
    )

    fig_circ = px.line(
        df_long, x='date', y='Total en Circulación',
        color='Tipo de Deuda',
        title='Evolución de la Deuda en Circulación por Tipo',
        labels={
            'date': 'Fecha',
            'Total en Circulación': 'Billones USD'
        },
    )
    fig_circ.update_layout(
        template='plotly_dark',
        title_x=0.5,
        yaxis_ticksuffix='T',
        legend={'orientation': 'h', 'y': -0.15},
        margin={'l': 60, 'r': 30, 't': 60, 'b': 60},
    )

    # ==========================================================
    # GRÁFICO 2: Muro de vencimientos (próximos 2 años)
    # ==========================================================
    fecha_limite_futuro = last_issue_date + pd.DateOffset(years=2)
    venc_futuros = df[
        (df['maturity_date'] > last_issue_date) &
        (df['maturity_date'] <= fecha_limite_futuro)
    ]

    if venc_futuros.empty:
        fig_wall = go.Figure()
        fig_wall.update_layout(
            template='plotly_dark',
            annotations=[{
                'text': 'Sin vencimientos en los próximos 2 años',
                'xref': 'paper', 'yref': 'paper',
                'x': 0.5, 'y': 0.5, 'showarrow': False,
                'font': {'size': 16, 'color': 'gray'}
            }]
        )
    else:
        muro = venc_futuros.groupby([
            pd.Grouper(key='maturity_date', freq='ME'),
            'security_type'
        ])['total_accepted'].sum().reset_index()
        muro['total_accepted'] = muro['total_accepted'] / 1e9

        fig_wall = px.bar(
            muro, x='maturity_date', y='total_accepted',
            color='security_type',
            title='Muro de Vencimientos (próximos 2 años)',
            labels={
                'maturity_date': 'Mes de Vencimiento',
                'total_accepted': 'Miles de Millones USD',
                'security_type': 'Tipo'
            },
            barmode='stack'
        )
        fig_wall.update_layout(
            template='plotly_dark',
            title_x=0.5,
            legend={'orientation': 'h', 'y': -0.15},
            margin={'l': 60, 'r': 30, 't': 60, 'b': 60},
        )

    return fig_circ, fig_wall
