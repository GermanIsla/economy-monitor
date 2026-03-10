# dashboard/pages/repo.py
# Página de visualización de datos de Repo Tri-Party
# Múltiples vistas: por tipo de colateral, por calidad, por origen, y equities

import dash
from dash import html, dcc, callback, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import select, func
from db.engine import get_session
from db.models.repo import RepoOperation
from dashboard.components.cards import kpi_card
from dashboard.components.charts import empty_figure, CHART_LAYOUT

dash.register_page(
    __name__,
    path="/repo",
    name="Repo",
    title="Economy Monitor | Repo"
)

# ============================================================
# Clasificaciones de colateral
# ============================================================
COLATERAL_EXTERNO = [
    'US Treasuries Strips', 'US Treasuries excluding Strips',
    'Agency CMOs', 'Agency Debentures & Strips', 'Agency MBS',
    'Municipality Debt'
]
COLATERAL_INTERNO = [
    'ABS Investment Grade', 'CMO Private Label Investment Grade',
    'International Securities', 'Money Market',
    'ABS Non Investment Grade', 'CMO Private Label Non Investment Grade',
    'CDOs', 'Corporates Investment Grade', 'Corporates Non Investment Grade',
    'Equities', 'Whole Loans', 'Other'
]

CALIDAD_ALTISIMA = ['US Treasuries Strips', 'US Treasuries excluding Strips']
CALIDAD_MEDIA = ['Agency CMOs', 'Agency Debentures & Strips', 'Agency MBS']
CALIDAD_MEDIA_BAJA = [
    'ABS Investment Grade', 'CMO Private Label Investment Grade',
    'Corporates Investment Grade',
    'International Securities', 'Money Market', 'Municipality Debt'
]
CALIDAD_BAJA = [
    'ABS Non Investment Grade', 'CMO Private Label Non Investment Grade',
    'Corporates Non Investment Grade'
]
CALIDAD_BAJISIMA = [
    'CDOs', 'Equities', 'Whole Loans', 'Other'
]

# Colores consistentes para las categorías de calidad
COLORS_QUALITY = {
    'Calidad Altísima': '#3b82f6',
    'Calidad Media': '#22c55e',
    'Calidad Media-Baja': '#eab308',
    'Calidad Baja': '#f97316',
    'Calidad Bajísima': '#ef4444',
}

QUALITY_ORDER = [
    'Calidad Altísima', 'Calidad Media', 'Calidad Media-Baja',
    'Calidad Baja', 'Calidad Bajísima'
]


# ============================================================
# Layout
# ============================================================
layout = dbc.Container([
    html.H2("Mercado de Repo Tri-Party", className="mb-1"),
    html.P(
        "Volumen, composición y calidad del colateral en el mercado de repo.",
        className="text-muted mb-4"
    ),
    html.Hr(),

    # --- Filtros ---
    dbc.Row([
        dbc.Col([
            html.Label("Vista:", className="fw-bold"),
            dcc.Dropdown(
                id="repo-view-filter",
                options=[
                    {"label": "Origen (Interno vs Externo)", "value": "origin"},
                    {"label": "Calidad del Colateral", "value": "quality"},
                    {"label": "Análisis de Riesgo (Calidad Baja)", "value": "risk"},
                    {"label": "Equities (detalle)", "value": "equities"},
                    {"label": "Todos los tipos", "value": "all"},
                ],
                value="origin",
                clearable=False
            ),
        ], width=3),
        dbc.Col([
            html.Label("Periodo:", className="fw-bold"),
            dcc.Dropdown(
                id="repo-period-filter",
                options=[
                    {"label": "6 meses", "value": 180},
                    {"label": "1 año", "value": 365},
                    {"label": "2 años", "value": 730},
                    {"label": "5 años", "value": 1825},
                    {"label": "Todo", "value": 0},
                ],
                value=730,
                clearable=False
            ),
        ], width=3),
    ], className="mb-4"),

    # --- KPI cards ---
    html.Div(id="repo-kpi-row", className="mb-4"),

    # --- Gráfico principal ---
    dbc.Row([
        dbc.Col([
            dbc.Card([dbc.CardBody([
                dcc.Graph(id="repo-main-chart")
            ])])
        ], width=12),
    ], className="mb-4"),

    # --- Gráfico secundario ---
    dbc.Row([
        dbc.Col([
            dbc.Card([dbc.CardBody([
                dcc.Graph(id="repo-secondary-chart")
            ])])
        ], width=12),
    ]),

], fluid=True)


# ============================================================
# Helpers
# ============================================================
def _load_repo_data(period_days: int) -> pd.DataFrame:
    """Lee datos de repo desde SQLite."""
    with get_session() as session:
        stmt = select(RepoOperation).order_by(RepoOperation.date)
        if period_days > 0:
            fecha_limite = datetime.now().date() - timedelta(days=period_days)
            stmt = stmt.where(RepoOperation.date >= fecha_limite)
        results = session.execute(stmt).scalars().all()

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame([{
        'date': r.date,
        'group_name': r.group_name,
        'collateral_value': r.collateral_value,
        'share_of_total': r.share_of_total,
    } for r in results])

    df['date'] = pd.to_datetime(df['date'])
    return df


def _classify_origin(group_name: str) -> str:
    if group_name in COLATERAL_EXTERNO:
        return 'Colateral Externo'
    elif group_name in COLATERAL_INTERNO:
        return 'Colateral Interno'
    return 'Sin Categoría'


def _classify_quality(group_name: str) -> str:
    if group_name in CALIDAD_ALTISIMA:
        return 'Calidad Altísima'
    elif group_name in CALIDAD_MEDIA:
        return 'Calidad Media'
    elif group_name in CALIDAD_MEDIA_BAJA:
        return 'Calidad Media-Baja'
    elif group_name in CALIDAD_BAJA:
        return 'Calidad Baja'
    elif group_name in CALIDAD_BAJISIMA:
        return 'Calidad Bajísima'
    return 'Sin Categoría'


def _base_layout(**overrides):
    """Crea un dict de layout base sin conflictos de keys."""
    base = dict(CHART_LAYOUT)
    base.update(overrides)
    return base


# ============================================================
# Callback principal
# ============================================================
@callback(
    Output("repo-kpi-row", "children"),
    Output("repo-main-chart", "figure"),
    Output("repo-secondary-chart", "figure"),
    Input("repo-view-filter", "value"),
    Input("repo-period-filter", "value"),
)
def update_repo(view, period_days):
    """Actualiza toda la página según la vista seleccionada."""

    df = _load_repo_data(period_days)

    if df.empty:
        empty = empty_figure("Sin datos. Ejecuta: python run_pipeline.py repo")
        no_kpi = dbc.Row([
            dbc.Col(kpi_card("Repo", "Sin datos", icon="bi-arrow-left-right"), width=3)
        ])
        return no_kpi, empty, empty

    # --- KPI cards (comunes a todas las vistas) ---
    latest_date = df['date'].max()
    df_latest = df[df['date'] == latest_date]
    total_volume = df_latest['collateral_value'].sum()

    equities_latest = df_latest[
        df_latest['group_name'] == 'Equities'
    ]['collateral_value'].sum()

    treasuries_latest = df_latest[
        df_latest['group_name'].isin(CALIDAD_ALTISIMA)
    ]['collateral_value'].sum()

    # Calcular % de colateral de baja calidad + bajísima
    df_latest_q = df_latest.copy()
    df_latest_q['quality'] = df_latest_q['group_name'].apply(_classify_quality)
    low_quality_vol = df_latest_q[
        df_latest_q['quality'].isin(['Calidad Baja', 'Calidad Bajísima', 'Calidad Media-Baja'])
    ]['collateral_value'].sum()
    pct_low = (low_quality_vol / total_volume * 100) if total_volume > 0 else 0

    from utils.helpers import format_amount
    kpi_row = dbc.Row([
        dbc.Col(kpi_card(
            "Volumen Total",
            format_amount(total_volume),
            icon="bi-arrow-left-right"
        ), width=3),
        dbc.Col(kpi_card(
            "US Treasuries",
            format_amount(treasuries_latest),
            icon="bi-bank"
        ), width=3),
        dbc.Col(kpi_card(
            "Equities",
            format_amount(equities_latest),
            icon="bi-graph-up-arrow"
        ), width=3),
        dbc.Col(kpi_card(
            "Colateral ≤ Media-Baja",
            f"{pct_low:.1f}%",
            delta_color="danger" if pct_low > 15 else "warning" if pct_low > 10 else "success",
            icon="bi-exclamation-triangle"
        ), width=3),
    ])

    # --- Generar gráficos según la vista ---
    if view == "origin":
        fig_main, fig_sec = _view_origin(df)
    elif view == "quality":
        fig_main, fig_sec = _view_quality(df)
    elif view == "risk":
        fig_main, fig_sec = _view_risk_analysis(df)
    elif view == "equities":
        fig_main, fig_sec = _view_equities(df)
    else:
        fig_main, fig_sec = _view_all(df)

    return kpi_row, fig_main, fig_sec


# ============================================================
# Vista: Origen (Interno vs Externo)
# ============================================================
def _view_origin(df: pd.DataFrame):
    df = df.copy()
    df['origin'] = df['group_name'].apply(_classify_origin)
    grouped = df.groupby(['date', 'origin'])['collateral_value'].sum().unstack().fillna(0)

    fig_main = go.Figure()
    colors = {'Colateral Externo': '#3b82f6', 'Colateral Interno': '#f59e0b'}

    for col in ['Colateral Externo', 'Colateral Interno']:
        if col in grouped.columns:
            fig_main.add_trace(go.Scatter(
                x=grouped.index, y=grouped[col],
                mode='lines', name=col,
                line=dict(color=colors.get(col), width=2),
                stackgroup='one'
            ))

    fig_main.update_layout(**_base_layout(
        title_text="Volumen de Repo por Origen del Colateral",
        yaxis_title="Volumen (miles de millones USD)",
        xaxis_title="Fecha",
    ))

    # Proporción
    df_pct = grouped.div(grouped.sum(axis=1), axis=0) * 100
    fig_sec = go.Figure()
    for col in ['Colateral Externo', 'Colateral Interno']:
        if col in df_pct.columns:
            fig_sec.add_trace(go.Scatter(
                x=df_pct.index, y=df_pct[col],
                mode='lines', name=col,
                line=dict(color=colors.get(col)),
                stackgroup='one'
            ))
    fig_sec.update_layout(**_base_layout(
        title_text="Proporción Interno vs Externo (%)",
        yaxis_title="% del Total",
        yaxis_range=[0, 100],
    ))

    return fig_main, fig_sec


# ============================================================
# Vista: Calidad del Colateral
# ============================================================
def _view_quality(df: pd.DataFrame):
    df = df.copy()
    df['quality'] = df['group_name'].apply(_classify_quality)
    grouped = df.groupby(['date', 'quality'])['collateral_value'].sum().unstack().fillna(0)

    fig_main = go.Figure()
    for q in QUALITY_ORDER:
        if q in grouped.columns:
            fig_main.add_trace(go.Scatter(
                x=grouped.index, y=grouped[q],
                mode='lines', name=q,
                line=dict(color=COLORS_QUALITY.get(q, '#888'), width=2),
            ))

    fig_main.update_layout(**_base_layout(
        title_text="Volumen de Repo por Calidad del Colateral",
        yaxis_title="Volumen (miles de millones USD)",
    ))

    # Proporción apilada de cada calidad
    total = grouped.sum(axis=1)
    df_pct = grouped.div(total, axis=0) * 100

    fig_sec = go.Figure()
    for q in QUALITY_ORDER:
        if q in df_pct.columns:
            fig_sec.add_trace(go.Scatter(
                x=df_pct.index, y=df_pct[q],
                mode='lines', name=q,
                line=dict(color=COLORS_QUALITY.get(q, '#888'), width=1),
                stackgroup='one',
            ))

    fig_sec.update_layout(**_base_layout(
        title_text="Composición por Calidad (% del Total)",
        yaxis_title="% del Total",
        yaxis_range=[0, 100],
    ))

    return fig_main, fig_sec


# ============================================================
# Vista: Análisis de Riesgo (NUEVA)
# ============================================================
def _view_risk_analysis(df: pd.DataFrame):
    """
    Análisis enfocado en la calidad inferior del colateral.
    Gráfico 1: Evolución del volumen por cada categoría de riesgo
    Gráfico 2: Porcentaje acumulado de baja calidad sobre el total
    """
    df = df.copy()
    df['quality'] = df['group_name'].apply(_classify_quality)
    grouped = df.groupby(['date', 'quality'])['collateral_value'].sum().unstack().fillna(0)
    total = grouped.sum(axis=1)

    # --- Gráfico 1: Volumen de las categorías de riesgo ---
    risk_categories = ['Calidad Altísima', 'Calidad Media','Calidad Media-Baja', 'Calidad Baja', 'Calidad Bajísima']

    fig_main = go.Figure()
    for q in risk_categories:
        if q in grouped.columns:
            fig_main.add_trace(go.Scatter(
                x=grouped.index, y=grouped[q],
                mode='lines', name=q,
                line=dict(color=COLORS_QUALITY.get(q, '#888'), width=2),
                #Comentado para quitar el apilado y volver a líneas individuales
                #stackgroup='one',
            ))

    fig_main.update_layout(**_base_layout(
        title_text="Volumen de Colateral por Debajo de Calidad Media (apilado)",
        yaxis_title="Volumen (miles de millones USD)",
        xaxis_title="Fecha",
    ))

    # --- Gráfico 2: % acumulado sobre el total ---
    '''
    fig_sec = go.Figure()

    # Línea individual para cada categoría
    for q in risk_categories:
        if q in grouped.columns:
            pct_q = (grouped[q] / total * 100).fillna(0)
            fig_sec.add_trace(go.Scatter(
                x=pct_q.index, y=pct_q,
                mode='lines', name=f"% {q}",
                line=dict(color=COLORS_QUALITY.get(q, '#888'), width=1.5),
            ))

    # Línea agregada: todo lo que es media-baja + baja + bajísima
    cols_risk = [q for q in risk_categories if q in grouped.columns]
    if cols_risk:
        total_risk = grouped[cols_risk].sum(axis=1)
        pct_total_risk = (total_risk / total * 100).fillna(0)
        fig_sec.add_trace(go.Scatter(
            x=pct_total_risk.index, y=pct_total_risk,
            mode='lines', name='TOTAL ≤ Media-Baja',
            line=dict(color='#ffffff', width=3),
            fill='tozeroy',
            fillcolor='rgba(239, 68, 68, 0.12)',
        ))

    fig_sec.update_layout(**_base_layout(
        title_text="Porcentaje de Colateral de Riesgo sobre el Total",
        yaxis_title="% del Total",
        xaxis_title="Fecha",
    ))
    '''
    fig_sec = go.Figure()

    cols_risk = [q for q in risk_categories if q in grouped.columns]
    if cols_risk:
        # Suma de las tres categorías de riesgo
        total_risk = grouped[cols_risk].sum(axis=1)
        pct_total_risk = (total_risk / total * 100).fillna(0)
        fig_sec.add_trace(go.Scatter(
            x=pct_total_risk.index, y=pct_total_risk,
            mode='lines', name='% Colateral ≤ Media-Baja',
            line=dict(color='#ef4444', width=2.5),
            fill='tozeroy',
            fillcolor='rgba(239, 68, 68, 0.15)',
        ))

        # Línea de referencia con el valor medio
        avg_pct = pct_total_risk.mean()
        fig_sec.add_hline(
            y=avg_pct, line_width=1, line_dash="dash",
            line_color="rgba(255, 255, 255, 0.4)",
            annotation_text=f"Media: {avg_pct:.1f}%",
            annotation_position="top right",
            annotation_font_color="rgba(255, 255, 255, 0.6)",
        )

    fig_sec.update_layout(**_base_layout(
        title_text="Colateral de Riesgo (Media-Baja + Baja + Bajísima) como % del Total",
        yaxis_title="% del Total",
        xaxis_title="Fecha",
        showlegend=False,
    ))

    return fig_main, fig_sec


# ============================================================
# Vista: Equities (detalle)
# ============================================================
def _view_equities(df: pd.DataFrame):
    df_eq = df[df['group_name'] == 'Equities'].sort_values('date')

    if df_eq.empty:
        empty = empty_figure("Sin datos de Equities")
        return empty, empty

    fig_main = go.Figure()
    fig_main.add_trace(go.Scatter(
        x=df_eq['date'], y=df_eq['collateral_value'],
        mode='lines', name='Volumen Equities',
        line=dict(color='#06b6d4', width=2),
        fill='tozeroy', fillcolor='rgba(6, 182, 212, 0.15)',
    ))
    fig_main.update_layout(**_base_layout(
        title_text="Volumen de Repo con Colateral de Equities",
        yaxis_title="Volumen (miles de millones USD)",
    ))

    # Cambio porcentual
    df_eq_copy = df_eq.copy()
    df_eq_copy['pct_change'] = df_eq_copy['collateral_value'].pct_change() * 100

    bar_colors = [
        'rgba(239, 68, 68, 0.7)' if v > 0 else 'rgba(34, 197, 94, 0.7)'
        for v in df_eq_copy['pct_change'].fillna(0)
    ]

    fig_sec = go.Figure()
    fig_sec.add_trace(go.Bar(
        x=df_eq_copy['date'], y=df_eq_copy['pct_change'],
        marker_color=bar_colors,
        name='Cambio %',
    ))
    fig_sec.add_hline(y=0, line_width=1, line_color="gray")
    fig_sec.update_layout(**_base_layout(
        title_text="Variación Porcentual del Volumen de Equities",
        yaxis_title="Cambio (%)",
        showlegend=False,
    ))

    return fig_main, fig_sec


# ============================================================
# Vista: Todos los tipos
# ============================================================
def _view_all(df: pd.DataFrame):
    grouped = df.groupby(['date', 'group_name'])['collateral_value'].sum().unstack().fillna(0)

    fig_main = go.Figure()
    for col in sorted(grouped.columns):
        fig_main.add_trace(go.Scatter(
            x=grouped.index, y=grouped[col],
            mode='lines', name=col,
            line=dict(width=1.5),
        ))

    fig_main.update_layout(
        template='plotly_dark',
        font={'family': 'system-ui, -apple-system, sans-serif'},
        title_text="Volumen de Repo por Tipo de Colateral",
        title_x=0.5,
        yaxis_title="Volumen (miles de millones USD)",
        margin={'l': 60, 'r': 200, 't': 60, 'b': 60},
        legend=dict(
            orientation='v', yanchor='top', y=1, xanchor='left', x=1.02,
            font=dict(size=10)
        ),
    )

    # Composición apilada últimos 6 meses
    fecha_6m = grouped.index.max() - pd.DateOffset(months=6)
    recent = grouped[grouped.index >= fecha_6m]

    fig_sec = go.Figure()
    for col in sorted(recent.columns):
        fig_sec.add_trace(go.Scatter(
            x=recent.index, y=recent[col],
            mode='lines', name=col,
            stackgroup='one',
            line=dict(width=0.5),
        ))
    fig_sec.update_layout(
        template='plotly_dark',
        font={'family': 'system-ui, -apple-system, sans-serif'},
        title_text="Composición Total (últimos 6 meses, apilado)",
        title_x=0.5,
        yaxis_title="Volumen (miles de millones USD)",
        margin={'l': 60, 'r': 200, 't': 60, 'b': 60},
        legend=dict(
            orientation='v', yanchor='top', y=1, xanchor='left', x=1.02,
            font=dict(size=10)
        ),
    )

    return fig_main, fig_sec