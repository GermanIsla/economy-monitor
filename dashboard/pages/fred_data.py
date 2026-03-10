# dashboard/pages/fred_data.py
# Página: Datos FRED — Balance Sheet de la Reserva Federal
# Primer gráfico: activos en cartera de la Fed por tipo (Tesoro + Agencias + MBS)

import dash
from dash import html, dcc, callback, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import select
from db.engine import get_session
from db.models.fed_balance import FedBalanceAsset
from dashboard.components.charts import apply_standard_layout, empty_figure

# --- Registro de página ---
dash.register_page(
    __name__,
    path="/fred-data",
    name="Datos FRED",
    title="Economy Monitor | Datos FRED"
)

# ------------------------------------------------------------------
# Texto explicativo (colapsable)
# ------------------------------------------------------------------
EXPLICACION_BALANCE = """
**¿Qué muestra este gráfico?**

Cuando la Reserva Federal (Fed) implementa programas de compra masiva de activos —
conocidos popularmente como *Quantitative Easing* (QE) — amplía su balance comprando
valores en el mercado abierto e inyectando liquidez al sistema financiero.

Los tres tipos de activos que aquí se representan son:

- 🔵 **Bonos del Tesoro (TREAST):** Deuda emitida por el gobierno federal estadounidense.
  Históricamente el activo dominante. Su compra masiva comenzó en noviembre de 2008 (QE1)
  y se aceleró en cada programa posterior.

- 🔴 **Deuda de Agencias Federales (FEDDT):** Valores emitidos por entidades patrocinadas
  por el gobierno (Fannie Mae, Freddie Mac, etc.). Protagonizaron el QE1 pero fueron
  abandonados progresivamente; su nivel ha caído a casi cero desde 2014.

- 🟢 **MBS — Valores Respaldados por Hipotecas (WSHOMCB):** Paquetes de hipotecas
  residenciales garantizados por agencias federales. Herramienta clave en el QE3 (2012)
  y en la respuesta a la pandemia de COVID-19 (2020). Transmiten directamente el estímulo
  al mercado hipotecario.

**Señales clave:**
- **Incrementos rápidos** → La Fed está en modo expansivo (QE activo)
- **Meseta o descenso gradual** → La Fed está en modo contractivo (*Quantitative Tightening*, QT),
  dejando vencer los activos sin reinvertir
- **Tamaño total del balance** → Indicador de cuánta liquidez ha inyectado la Fed en el sistema
"""

# ------------------------------------------------------------------
# Layout
# ------------------------------------------------------------------
layout = dbc.Container([
    html.H2("Datos FRED — Reserva Federal", className="mb-1"),
    html.P(
        "Series económicas del Federal Reserve Economic Data (FRED) del Banco de la Reserva Federal de St. Louis.",
        className="text-muted mb-4"
    ),
    html.Hr(),

    # --- Filtro de periodo ---
    dbc.Row([
        dbc.Col([
            html.Label("Periodo:", className="fw-bold"),
            dcc.Dropdown(
                id="fred-periodo-filter",
                options=[
                    {"label": "5 años", "value": 1825},
                    {"label": "10 años", "value": 3650},
                    {"label": "15 años", "value": 5475},
                    {"label": "Todo el histórico", "value": 0},
                ],
                value=0,
                clearable=False,
                style={"width": "200px"}
            ),
        ], width="auto"),
    ], className="mb-4"),

    # --- Sección: Balance Sheet Fed ---
    dbc.Row([
        dbc.Col([
            html.H4("Balance Sheet de la Reserva Federal", className="mb-2"),
            html.P(
                "Activos en cartera: valores adquiridos en programas QE (H.4.1 — nivel semanal, en miles de millones USD)",
                className="text-muted small mb-3"
            ),
        ])
    ]),

    # Gráfico principal
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    dcc.Graph(id="fred-balance-chart", style={"height": "500px"})
                ])
            ])
        ], width=12)
    ]),

    # KPI cards
    dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("Bonos del Tesoro", className="text-muted small mb-1"),
            html.H4(id="fred-kpi-treast", className="mb-0 text-primary"),
        ])), width=4, className="mt-3"),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("Deuda de Agencias", className="text-muted small mb-1"),
            html.H4(id="fred-kpi-feddt", className="mb-0 text-danger"),
        ])), width=4, className="mt-3"),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("MBS (Hipotecas)", className="text-muted small mb-1"),
            html.H4(id="fred-kpi-mbs", className="mb-0 text-success"),
        ])), width=4, className="mt-3"),
    ], className="mb-4"),

    # Texto explicativo colapsable
    dbc.Row([
        dbc.Col([
            dbc.Button(
                "📖 ¿Qué significa este gráfico?",
                id="fred-balance-collapse-btn",
                color="secondary",
                outline=True,
                size="sm",
                className="mb-2"
            ),
            dbc.Collapse(
                dbc.Card(dbc.CardBody(
                    dcc.Markdown(EXPLICACION_BALANCE)
                ), className="mt-1 border-secondary"),
                id="fred-balance-collapse",
                is_open=False,
            ),
        ], width=12),
    ], className="mb-5"),

    # Segundo gráfico: variación semanal
    dbc.Row([
        dbc.Col([
            html.H4("Variación Semanal por Tipo de Activo", className="mb-2 mt-4"),
            html.P(
                "Cambio neto respecto a la semana anterior (miles de millones USD). "
                "Positivo = compras netas / reinversión. Negativo = vencimientos sin reinvertir (QT).",
                className="text-muted small mb-3"
            ),
        ])
    ]),
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    dcc.Graph(id="fred-balance-delta-chart", style={"height": "400px"})
                ])
            ])
        ], width=12)
    ], className="mb-4"),

], fluid=True)


# ------------------------------------------------------------------
# Callbacks
# ------------------------------------------------------------------
@callback(
    Output("fred-balance-chart", "figure"),
    Output("fred-kpi-treast", "children"),
    Output("fred-kpi-feddt", "children"),
    Output("fred-kpi-mbs", "children"),
    Output("fred-balance-delta-chart", "figure"),
    Input("fred-periodo-filter", "value"),
)
def update_balance_chart(periodo_dias):
    """Carga datos de fed_balance_assets y genera el gráfico de áreas apiladas."""

    with get_session() as session:
        stmt = select(FedBalanceAsset).order_by(FedBalanceAsset.date)
        results = session.execute(stmt).scalars().all()

    if not results:
        fig = empty_figure("Sin datos — ejecuta: python run_pipeline.py fed_balance")
        return fig, "N/A", "N/A", "N/A"

    df = pd.DataFrame([{
        "date": r.date,
        "series_id": r.series_id,
        "series_name": r.series_name,
        "value": r.value,
    } for r in results])

    # Filtrar por periodo
    if periodo_dias and periodo_dias > 0:
        fecha_limite = datetime.now().date() - timedelta(days=periodo_dias)
        df = df[df["date"] >= fecha_limite]

    if df.empty:
        return empty_figure("Sin datos para el periodo seleccionado"), "N/A", "N/A", "N/A"

    # Pivotar para el gráfico de áreas
    df_pivot = df.pivot_table(index="date", columns="series_id", values="value", aggfunc="first")
    df_pivot = df_pivot.sort_index()

    # Orden y colores consistentes
    series_config = {
        "TREAST":  {"nombre": "Bonos del Tesoro", "color": "#4c78a8"},
        "FEDDT":   {"nombre": "Agencias Federales", "color": "#e45756"},
        "WSHOMCB": {"nombre": "MBS (Hipotecas)", "color": "#54a24b"},
    }

    fig = go.Figure()

    for sid, cfg in series_config.items():
        if sid not in df_pivot.columns:
            continue
        fig.add_trace(go.Scatter(
            x=df_pivot.index,
            y=df_pivot[sid],
            name=cfg["nombre"],
            mode="lines",
            stackgroup="one",
            line={"width": 0.5, "color": cfg["color"]},
            fillcolor=cfg["color"].replace(")", ", 0.7)").replace("rgb(", "rgba("),
            hovertemplate=f"<b>{cfg['nombre']}</b><br>%{{x}}<br>$%{{y:,.1f}} MM USD<extra></extra>",
        ))

    # Anotar los programas QE
    from datetime import date as date_type
    qe_events = [
        {"x": date_type(2008, 11, 25), "label": "QE1"},
        {"x": date_type(2010, 11, 3),  "label": "QE2"},
        {"x": date_type(2012, 9, 13),  "label": "QE3"},
        {"x": date_type(2020, 3, 15),  "label": "QE4 (COVID)"},
    ]
    for ev in qe_events:
        fig.add_shape(
            type="line",
            x0=ev["x"], x1=ev["x"],
            y0=0, y1=1,
            xref="x", yref="paper",
            line={"dash": "dot", "color": "rgba(255,255,255,0.3)", "width": 1},
        )
        fig.add_annotation(
            x=ev["x"], y=1,
            xref="x", yref="paper",
            text=ev["label"],
            showarrow=False,
            font={"size": 10, "color": "rgba(255,255,255,0.6)"},
            yanchor="bottom",
        )
    apply_standard_layout(fig, "Activos en Cartera — Balance Sheet de la Fed (MM USD)")
    fig.update_layout(
        yaxis_title="Miles de millones USD",
        xaxis_title="",
        hovermode="x unified",
        legend={"orientation": "h", "y": -0.15},
    )

    # KPIs: último valor disponible por serie
    def fmt_kpi(sid):
        if sid not in df_pivot.columns or df_pivot[sid].dropna().empty:
            return "N/A"
        val = df_pivot[sid].dropna().iloc[-1]
        if val >= 1000:
            return f"${val/1000:.2f} B"
        return f"${val:.0f} MM"


    # --- Gráfico de variación semanal ---
    series_config = {
        "TREAST":  {"nombre": "Bonos del Tesoro", "color": "#4c78a8"},
        "FEDDT":   {"nombre": "Agencias Federales", "color": "#e45756"},
        "WSHOMCB": {"nombre": "MBS (Hipotecas)",    "color": "#54a24b"},
    }

    fig_delta = go.Figure()
    for sid, cfg in series_config.items():
        if sid not in df_pivot.columns:
            continue
        delta = df_pivot[sid].diff()
        fig_delta.add_trace(go.Bar(
            x=df_pivot.index,
            y=delta,
            name=cfg["nombre"],
            marker_color=cfg["color"],
            hovertemplate=f"<b>{cfg['nombre']}</b><br>%{{x}}<br>%{{y:+,.1f}} MM USD<extra></extra>",
        ))

    apply_standard_layout(fig_delta, "Variación Semanal de Activos en Cartera (MM USD)")
    fig_delta.update_layout(
        barmode="group",
        yaxis_title="Variación (MM USD)",
        xaxis_title="",
        hovermode="x unified",
        legend={"orientation": "h", "y": -0.15},
    )

    return fig, fmt_kpi("TREAST"), fmt_kpi("FEDDT"), fmt_kpi("WSHOMCB"), fig_delta


@callback(
    Output("fred-balance-collapse", "is_open"),
    Input("fred-balance-collapse-btn", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_explicacion(n_clicks):
    """Abre o cierra el texto explicativo."""
    return (n_clicks or 0) % 2 == 1
