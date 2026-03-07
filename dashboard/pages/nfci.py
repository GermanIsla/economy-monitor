# dashboard/pages/nfci.py
# Página del indicador NFCI — Condiciones Financieras
# Equivalente a nfcicredit_visualicer.py del proyecto original

import dash
from dash import html, dcc, callback, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import select
from db.engine import get_session
from db.models.nfci import NFCIReading
from dashboard.components.cards import kpi_card
from dashboard.components.charts import empty_figure, CHART_LAYOUT

dash.register_page(
    __name__,
    path="/nfci",
    name="NFCI",
    title="Economy Monitor | NFCI"
)

layout = dbc.Container([
    html.H2("Indicador NFCI (Condiciones Financieras)", className="mb-1"),
    html.P([
        "Evolución del National Financial Conditions Index de la Fed de Chicago. ",
        "Valores positivos → condiciones restrictivas. ",
        "Valores negativos → condiciones laxas."
    ], className="text-muted mb-4"),
    html.Hr(),

    # --- Filtros ---
    dbc.Row([
        dbc.Col([
            html.Label("Serie:", className="fw-bold"),
            dcc.Dropdown(
                id="nfci-series-filter",
                options=[
                    {"label": "NFCI (Índice General)", "value": "NFCI"},
                    {"label": "NFCI Crédito (Subíndice)", "value": "NFCICREDIT"},
                    {"label": "Ambas series", "value": "ALL"},
                ],
                value="ALL",
                clearable=False
            ),
        ], width=3),
        dbc.Col([
            html.Label("Periodo:", className="fw-bold"),
            dcc.Dropdown(
                id="nfci-period-filter",
                options=[
                    {"label": "6 meses", "value": 180},
                    {"label": "1 año", "value": 365},
                    {"label": "2 años", "value": 730},
                    {"label": "5 años", "value": 1825},
                    {"label": "10 años", "value": 3650},
                    {"label": "Todo el histórico", "value": 0},
                ],
                value=730,
                clearable=False
            ),
        ], width=3),
    ], className="mb-4"),

    # --- KPI cards ---
    html.Div(id="nfci-kpi-row", className="mb-4"),

    # --- Gráfico principal ---
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    dcc.Graph(id="nfci-main-chart")
                ])
            ])
        ], width=12),
    ], className="mb-4"),

    # --- Gráfico de variación semanal ---
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Variación Semanal", className="card-title"),
                    dcc.Graph(id="nfci-change-chart")
                ])
            ])
        ], width=12),
    ]),

], fluid=True)


def _load_nfci_data(series_filter: str, period_days: int) -> pd.DataFrame:
    """Lee datos del NFCI desde SQLite y aplica filtros."""
    with get_session() as session:
        stmt = select(NFCIReading).order_by(NFCIReading.date)

        if series_filter != "ALL":
            stmt = stmt.where(NFCIReading.indicator_name == series_filter)

        results = session.execute(stmt).scalars().all()

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame([{
        'date': r.date,
        'indicator_name': r.indicator_name,
        'value': r.value,
    } for r in results])

    df['date'] = pd.to_datetime(df['date'])

    # Filtrar por periodo
    if period_days > 0:
        fecha_limite = datetime.now() - timedelta(days=period_days)
        df = df[df['date'] >= fecha_limite]

    return df


def _analyze_trend(values: pd.Series, weeks: int = 8) -> tuple[str, str]:
    """
    Analiza la tendencia de los últimos N valores.
    Retorna (texto_tendencia, color_badge).
    """
    if len(values) < weeks:
        return "Sin datos suficientes", "secondary"

    recent = values.tail(weeks)
    change = recent.iloc[-1] - recent.iloc[0]
    avg = recent.mean()

    if avg > 0:
        if change > 0.1:
            return "Alcista Fuerte (restrictivo)", "danger"
        elif change > 0:
            return "Alcista (restrictivo)", "warning"
        else:
            return "Estable (restrictivo)", "warning"
    else:
        if change < -0.1:
            return "Bajista Fuerte (laxo)", "success"
        elif change < 0:
            return "Bajista (laxo)", "info"
        else:
            return "Estable (laxo)", "info"


@callback(
    Output("nfci-kpi-row", "children"),
    Output("nfci-main-chart", "figure"),
    Output("nfci-change-chart", "figure"),
    Input("nfci-series-filter", "value"),
    Input("nfci-period-filter", "value"),
)
def update_nfci(series_filter, period_days):
    """Actualiza todos los componentes de la página NFCI."""

    df = _load_nfci_data(series_filter, period_days)

    if df.empty:
        empty = empty_figure("Sin datos. Ejecuta: python run_pipeline.py nfci")
        no_data_kpi = dbc.Row([
            dbc.Col(kpi_card("NFCI", "Sin datos", icon="bi-activity"), width=3),
        ])
        return no_data_kpi, empty, empty

    # ============================================================
    # KPI CARDS
    # ============================================================
    kpi_cards = []

    for indicator in df['indicator_name'].unique():
        df_ind = df[df['indicator_name'] == indicator].sort_values('date')

        if df_ind.empty:
            continue

        last_value = df_ind['value'].iloc[-1]
        last_date = df_ind['date'].iloc[-1]

        # Cambio respecto a la semana anterior
        if len(df_ind) >= 2:
            prev_value = df_ind['value'].iloc[-2]
            weekly_change = last_value - prev_value
            delta_text = f"{weekly_change:+.3f}"
            delta_color = "danger" if weekly_change > 0 else "success"
        else:
            delta_text = None
            delta_color = "secondary"

        # Tendencia
        trend_text, trend_color = _analyze_trend(df_ind['value'])

        kpi_cards.append(dbc.Col([
            kpi_card(
                f"{indicator}",
                f"{last_value:.3f}",
                delta=delta_text,
                delta_color=delta_color,
                icon="bi-activity"
            )
        ], width=3))

        kpi_cards.append(dbc.Col([
            kpi_card(
                f"Tendencia {indicator}",
                trend_text,
                icon="bi-arrow-right"
            )
        ], width=3))

    kpi_row = dbc.Row(kpi_cards)

    # ============================================================
    # GRÁFICO PRINCIPAL — Evolución temporal
    # ============================================================
    fig_main = go.Figure()

    colors = {
        'NFCI': '#6366f1',
        'NFCICREDIT': '#06b6d4',
    }

    for indicator in df['indicator_name'].unique():
        df_ind = df[df['indicator_name'] == indicator].sort_values('date')
        fig_main.add_trace(go.Scatter(
            x=df_ind['date'],
            y=df_ind['value'],
            mode='lines',
            name=indicator,
            line=dict(
                color=colors.get(indicator, '#8b5cf6'),
                width=2
            ),
        ))

    # Línea horizontal en cero (nivel promedio histórico)
    fig_main.add_hline(
        y=0,
        line_width=1,
        line_dash="dash",
        line_color="rgba(255, 100, 100, 0.6)",
        annotation_text="Nivel promedio (0)",
        annotation_position="bottom right",
        annotation_font_color="rgba(255, 100, 100, 0.8)",
    )

    # Zonas de color: restrictivo (>0) y laxo (<0)
    y_min = df['value'].min()
    y_max = df['value'].max()
    margin = abs(y_max - y_min) * 0.1

    fig_main.add_hrect(
        y0=0, y1=y_max + margin,
        fillcolor="rgba(239, 68, 68, 0.05)",
        line_width=0,
        annotation_text="Restrictivo",
        annotation_position="top left",
        annotation_font_size=11,
        annotation_font_color="rgba(239, 68, 68, 0.5)",
    )
    fig_main.add_hrect(
        y0=y_min - margin, y1=0,
        fillcolor="rgba(34, 197, 94, 0.05)",
        line_width=0,
        annotation_text="Laxo",
        annotation_position="bottom left",
        annotation_font_size=11,
        annotation_font_color="rgba(34, 197, 94, 0.5)",
    )

    fig_main.update_layout(
        **CHART_LAYOUT,
        title_text="Evolución del Indicador NFCI",
        yaxis_title="Valor del Índice",
        xaxis_title="Fecha",
        hovermode="x unified",
    )

    # ============================================================
    # GRÁFICO DE VARIACIÓN SEMANAL
    # ============================================================
    fig_change = go.Figure()

    for indicator in df['indicator_name'].unique():
        df_ind = df[df['indicator_name'] == indicator].sort_values('date').copy()
        df_ind['change'] = df_ind['value'].diff()

        # Colores condicionales: rojo si sube (restrictivo), verde si baja
        bar_colors = [
            'rgba(239, 68, 68, 0.7)' if c > 0 else 'rgba(34, 197, 94, 0.7)'
            for c in df_ind['change'].fillna(0)
        ]

        fig_change.add_trace(go.Bar(
            x=df_ind['date'],
            y=df_ind['change'],
            name=f"Δ {indicator}",
            marker_color=bar_colors,
            opacity=0.8,
        ))

    fig_change.add_hline(y=0, line_width=1, line_color="gray")

    fig_change.update_layout(
        **CHART_LAYOUT,
        title_text="Cambio Semanal del NFCI",
        yaxis_title="Variación",
        xaxis_title="Fecha",
        barmode='group',
        showlegend=False,
    )

    return kpi_row, fig_main, fig_change
