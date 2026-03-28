# dashboard/pages/cot.py
# Dashboard de Commitments of Traders (COT) — Disaggregated Combined, CFTC

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html
from datetime import datetime, timedelta
from sqlalchemy import select

from dashboard.components.charts import apply_standard_layout, empty_figure
from db.engine import get_session
from db.models.cot import COTReport
from db.models.commodity_price import CommodityPrice

dash.register_page(
    __name__,
    path="/cot",
    name="COT — Materias Primas",
    title="Economy Monitor | COT"
)

# ---------------------------------------------------------------------------
# Opciones de los filtros
# ---------------------------------------------------------------------------
COMMODITY_OPTIONS = [
    # Energía
    {"label": "🛢️  WTI Crude Oil",             "value": "WTI-PHYSICAL"},
    {"label": "🛢️  WTI Crude Oil (histórico)",  "value": "CRUDE OIL, LIGHT SWEET-WTI"},
    {"label": "🔥  Natural Gas (NYMEX)",         "value": "NAT GAS NYME"},
    {"label": "🔥  Henry Hub",                   "value": "HENRY HUB"},
    {"label": "🔥  Henry Hub Penultimate",        "value": "HENRY HUB PENULTIMATE NAT GAS"},
    {"label": "⛽  Heating Oil",                 "value": "NO. 2 HEATING OIL"},
    {"label": "⛽  Gasoline (RBOB)",             "value": "GASOLINE BLENDSTOCK (RBOB)"},
    # Metales
    {"label": "🥇  Gold",                        "value": "GOLD"},
    {"label": "🥈  Silver",                      "value": "SILVER"},
    {"label": "🔩  Copper",                      "value": "COPPER- #1"},
    {"label": "💿  Platinum",                    "value": "PLATINUM"},
    {"label": "💿  Palladium",                   "value": "PALLADIUM"},
    # Granos
    {"label": "🌽  Corn",                        "value": "CORN"},
    {"label": "🌾  Wheat (SRW)",                 "value": "WHEAT-SRW"},
    {"label": "🌾  Wheat (HRW)",                 "value": "WHEAT-HRW"},
    {"label": "🌾  Wheat (Spring)",              "value": "WHEAT-HRSpring"},
    {"label": "🫘  Soybeans",                    "value": "SOYBEANS"},
    {"label": "🫙  Soybean Oil",                 "value": "SOYBEAN OIL"},
    {"label": "🫙  Soybean Meal",                "value": "SOYBEAN MEAL"},
]

PERIOD_OPTIONS = [
    {"label": "1 año",    "value": 365},
    {"label": "2 años",   "value": 730},
    {"label": "5 años",   "value": 1825},
    {"label": "Todo",     "value": 0},
]

# Colores por categoría de trader — consistentes en todos los gráficos
TRADER_COLORS = {
    'Managed Money':      '#00b4d8',  # azul claro
    'Producer/Merchant':  '#f77f00',  # naranja
    'Swap Dealers':       '#9b5de5',  # violeta
    'Other Reportable':   '#43aa8b',  # verde
    'Non-Reportable':     '#adb5bd',  # gris
}

# Mapeo contrato COT → series_id de precios
COT_TO_PRICE_SERIES = {
    'WTI-PHYSICAL':                  'WTI',
    'CRUDE OIL, LIGHT SWEET-WTI':    'WTI',
    'NAT GAS NYME':                  'NATURAL_GAS',
    'HENRY HUB':                     'NATURAL_GAS',
    'HENRY HUB PENULTIMATE NAT GAS': 'NATURAL_GAS',
    'GOLD':                          'GOLD',
    'SILVER':                        'SILVER',
    'COPPER- #1':                    'COPPER',
    'WHEAT-SRW':                     'WHEAT',
    'WHEAT-HRW':                     'WHEAT',
    'WHEAT-HRSpring':                'WHEAT',
    'CORN':                          'CORN',
    'SOYBEANS':                      None,  # sin cobertura AV gratuita
    'SOYBEAN OIL':                   None,
    'SOYBEAN MEAL':                  None,
    'NO. 2 HEATING OIL':             None,
    'GASOLINE BLENDSTOCK (RBOB)':    None,
    'PLATINUM':                      None,
    'PALLADIUM':                     None,
}

PRICE_UNITS = {
    'WTI':         'USD/barril',
    'NATURAL_GAS': 'USD/MMBtu',
    'GOLD':        'USD/oz',
    'SILVER':      'USD/oz',
    'COPPER':      'USD/lb',
    'WHEAT':       'USD/bushel',
    'CORN':        'USD/bushel',
}

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
layout = dbc.Container([
    html.H2("Commitments of Traders — Materias Primas", className="mb-1"),
    html.P(
        "Posicionamiento semanal de los grandes traders en futuros y opciones. "
        "Fuente: CFTC Disaggregated Combined (futuros + opciones). "
        "Publicación: viernes con datos del martes anterior.",
        className="text-muted mb-4"
    ),
    html.Hr(),

    # --- Filtros ---
    dbc.Row([
        dbc.Col([
            html.Label("Contrato:", className="fw-bold"),
            dcc.Dropdown(
                id="cot-commodity-filter",
                options=COMMODITY_OPTIONS,
                value="WTI-PHYSICAL",
                clearable=False,
            ),
        ], width=5),
        dbc.Col([
            html.Label("Periodo:", className="fw-bold"),
            dcc.Dropdown(
                id="cot-period-filter",
                options=PERIOD_OPTIONS,
                value=730,
                clearable=False,
            ),
        ], width=3),
    ], className="mb-4"),

    # --- KPI cards ---
    dbc.Row(id="cot-kpi-row", className="mb-4"),

    # --- Tabs ---
    dbc.Tabs([

        # Pestaña 1: Posicionamiento neto
        dbc.Tab(label="Posicionamiento Neto", tab_id="tab-net", children=[
            dbc.Row([
                dbc.Col([
                    dbc.Card(dbc.CardBody([
                        dcc.Graph(id="cot-net-positions-chart")
                    ]))
                ], width=12),
            ], className="mt-3"),
            dbc.Row([
                dbc.Col([
                    dbc.Card(dbc.CardBody([
                        dcc.Graph(id="cot-net-changes-chart")
                    ]))
                ], width=12),
            ], className="mt-3"),

            # Texto explicativo
            dbc.Row([
                dbc.Col([
                    dbc.Accordion([
                        dbc.AccordionItem(
                            title="¿Cómo interpretar el posicionamiento neto?",
                            children=[
                                html.P([
                                    html.Strong("Posición neta = Longs − Shorts"), " de cada categoría de trader."
                                ]),
                                html.P([
                                    html.Strong("Managed Money (hedge funds, CTAs):"),
                                    " Es la categoría más seguida como señal de sentimiento especulativo. "
                                    "Una posición neta muy positiva indica consenso alcista extremo "
                                    "(posible señal de reversión si el mercado ya ha subido mucho). "
                                    "Una posición neta muy negativa indica pánico vendedor."
                                ]),
                                html.P([
                                    html.Strong("Producer/Merchant:"),
                                    " Operadores comerciales que cubren su exposición física. "
                                    "Suelen estar cortos cuando el precio es alto (cubren producción futura) "
                                    "y reducen su cobertura cuando el precio cae. "
                                    "Se consideran el 'dinero inteligente' con acceso a información del mercado físico."
                                ]),
                                html.P([
                                    html.Strong("Swap Dealers:"),
                                    " Bancos y dealers que gestionan el riesgo de sus libros OTC. "
                                    "Su posición refleja el agregado de sus clientes institucionales."
                                ]),
                                html.P([
                                    html.Strong("Señal clásica de reversión:"),
                                    " Cuando Managed Money alcanza un extremo histórico en una dirección "
                                    "y los Producers/Merchants están en el lado contrario, "
                                    "el mercado suele estar sobrecomprado/sobrevendido."
                                ]),
                            ]
                        )
                    ], start_collapsed=True)
                ], width=12),
            ], className="mt-2"),
        ]),

        # Pestaña 2: Interés Abierto
        dbc.Tab(label="Interés Abierto", tab_id="tab-oi", children=[
            dbc.Row([
                dbc.Col([
                    dbc.Card(dbc.CardBody([
                        dcc.Graph(id="cot-open-interest-chart")
                    ]))
                ], width=12),
            ], className="mt-3"),
            dbc.Row([
                dbc.Col([
                    dbc.Card(dbc.CardBody([
                        dcc.Graph(id="cot-oi-composition-chart")
                    ]))
                ], width=12),
            ], className="mt-3"),
        ]),

    ], id="cot-tabs", active_tab="tab-net"),

], fluid=True)


# ---------------------------------------------------------------------------
# Helper: carga de datos desde la DB
# ---------------------------------------------------------------------------
def _load_cot_data(commodity: str, period_days: int) -> pd.DataFrame:
    """Lee datos COT de la DB y aplica el filtro de periodo."""
    with get_session() as session:
        stmt = (
            select(COTReport)
            .where(COTReport.contract_market_name == commodity)
            .order_by(COTReport.report_date)
        )
        rows = session.execute(stmt).scalars().all()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([{
        'date':                r.report_date,
        'open_interest':       r.open_interest,
        'prod_merc_long':      r.prod_merc_long,
        'prod_merc_short':     r.prod_merc_short,
        'swap_long':           r.swap_long,
        'swap_short':          r.swap_short,
        'm_money_long':        r.m_money_long,
        'm_money_short':       r.m_money_short,
        'other_rept_long':     r.other_rept_long,
        'other_rept_short':    r.other_rept_short,
        'nonrept_long':        r.nonrept_long,
        'nonrept_short':       r.nonrept_short,
        'change_open_interest':r.change_open_interest,
        'change_m_money_long': r.change_m_money_long,
        'change_m_money_short':r.change_m_money_short,
    } for r in rows])

    if period_days > 0:
        cutoff = datetime.now().date() - timedelta(days=period_days)
        df = df[df['date'] >= cutoff]

    # Calcular posiciones netas
    df['net_prod_merc']   = df['prod_merc_long']  - df['prod_merc_short']
    df['net_swap']        = df['swap_long']        - df['swap_short']
    df['net_m_money']     = df['m_money_long']     - df['m_money_short']
    df['net_other_rept']  = df['other_rept_long']  - df['other_rept_short']
    df['net_nonrept']     = df['nonrept_long']      - df['nonrept_short']

    return df

def _load_price_data(series_id: str, period_days: int) -> pd.DataFrame:
    """Carga precios de la DB para una serie dada."""
    if not series_id:
        return pd.DataFrame()
    with get_session() as session:
        stmt = (
            select(CommodityPrice)
            .where(CommodityPrice.series_id == series_id)
            .order_by(CommodityPrice.date)
        )
        rows = session.execute(stmt).scalars().all()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([{'date': r.date, 'price': r.price} for r in rows])

    if period_days > 0:
        cutoff = datetime.now().date() - timedelta(days=period_days)
        df = df[df['date'] >= cutoff]

    return df

# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
@callback(
    Output("cot-kpi-row", "children"),
    Output("cot-net-positions-chart", "figure"),
    Output("cot-net-changes-chart", "figure"),
    Output("cot-open-interest-chart", "figure"),
    Output("cot-oi-composition-chart", "figure"),
    Input("cot-commodity-filter", "value"),
    Input("cot-period-filter", "value"),
)
def update_cot_charts(commodity, period_days):
    if not commodity:
        empty = empty_figure()
        return [], empty, empty, empty, empty

    df = _load_cot_data(commodity, period_days)

    if df.empty:
        msg = f"Sin datos para '{commodity}'. Ejecuta: python run_pipeline.py cot --full"
        empty = empty_figure(msg)
        return _no_data_kpis(), empty, empty, empty, empty

    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    kpis = _build_kpi_cards(last, prev)

    # --- Gráfico 1: Posicionamiento neto + overlay precio ---
    fig_net = go.Figure()

    # Trazas de posicionamiento (eje izquierdo)
    series = [
        ('net_m_money',    'Managed Money',     TRADER_COLORS['Managed Money']),
        ('net_prod_merc',  'Producer/Merchant', TRADER_COLORS['Producer/Merchant']),
        ('net_swap',       'Swap Dealers',      TRADER_COLORS['Swap Dealers']),
        ('net_other_rept', 'Other Reportable',  TRADER_COLORS['Other Reportable']),
    ]
    for col, label, color in series:
        if col in df.columns and df[col].notna().any():
            fig_net.add_trace(go.Scatter(
                x=df['date'], y=df[col],
                name=label,
                line=dict(color=color, width=1.5),
                mode='lines',
                yaxis='y1',
            ))

    # Línea de cero
    fig_net.add_shape(
        type='line', x0=df['date'].min(), x1=df['date'].max(),
        y0=0, y1=0,
        line=dict(color='rgba(255,255,255,0.3)', width=1, dash='dot')
    )

    # Overlay precio (eje derecho)
    price_series_id = COT_TO_PRICE_SERIES.get(commodity)
    df_price = _load_price_data(price_series_id, period_days)

    if not df_price.empty:
        unit = PRICE_UNITS.get(price_series_id, '')
        fig_net.add_trace(go.Scatter(
            x=df_price['date'],
            y=df_price['price'],
            name=f'Precio ({unit})',
            line=dict(color='#ffffff', width=1.5, dash='dot'),
            opacity=0.7,
            yaxis='y2',
        ))
        fig_net.update_layout(
            yaxis2=dict(
                title=f'Precio ({unit})',
                overlaying='y',
                side='right',
                showgrid=False,
                tickfont=dict(color='#aaaaaa'),
                title_font=dict(color='#aaaaaa'),
            )
        )

    apply_standard_layout(fig_net, f"Posicionamiento Neto — {commodity}")
    fig_net.update_layout(
        yaxis_title="Contratos",
        hovermode='x unified',
        legend=dict(orientation='h', y=-0.15),
    )

    # --- Gráfico 2: Cambio semanal Managed Money ---
    df['change_net_mm'] = df['change_m_money_long'] - df['change_m_money_short']
    colors_bar = ['#00b4d8' if v >= 0 else '#e63946'
                  for v in df['change_net_mm'].fillna(0)]
    fig_changes = go.Figure()
    fig_changes.add_trace(go.Bar(
        x=df['date'], y=df['change_net_mm'],
        name='Cambio semanal net MM',
        marker_color=colors_bar,
        opacity=0.8,
    ))
    apply_standard_layout(fig_changes,
        f"Cambio Semanal — Managed Money Net ({commodity})")
    fig_changes.update_layout(yaxis_title="Δ Contratos", hovermode='x unified')

    # --- Gráfico 3: Open Interest ---
    fig_oi = go.Figure()
    fig_oi.add_trace(go.Scatter(
        x=df['date'], y=df['open_interest'],
        name='Open Interest Total',
        fill='tozeroy',
        line=dict(color='#ffd166', width=1.5),
        fillcolor='rgba(255,209,102,0.15)',
    ))
    apply_standard_layout(fig_oi, f"Interés Abierto Total — {commodity}")
    fig_oi.update_layout(yaxis_title="Contratos")

    # --- Gráfico 4: Composición OI (longs apilados) ---
    fig_comp = go.Figure()
    long_series = [
        ('prod_merc_long',  'Prod/Merch Longs',  TRADER_COLORS['Producer/Merchant']),
        ('swap_long',       'Swap Longs',         TRADER_COLORS['Swap Dealers']),
        ('m_money_long',    'MM Longs',           TRADER_COLORS['Managed Money']),
        ('other_rept_long', 'Other Longs',        TRADER_COLORS['Other Reportable']),
        ('nonrept_long',    'Non-Rept Longs',     TRADER_COLORS['Non-Reportable']),
    ]
    for col, label, color in long_series:
        if col in df.columns and df[col].notna().any():
            fig_comp.add_trace(go.Bar(
                x=df['date'], y=df[col],
                name=label, marker_color=color, opacity=0.85,
            ))
    apply_standard_layout(fig_comp,
        f"Composición del Open Interest (Longs) — {commodity}")
    fig_comp.update_layout(barmode='stack', yaxis_title="Contratos")

    return kpis, fig_net, fig_changes, fig_oi, fig_comp


def _build_kpi_cards(last, prev):
    """Construye las tarjetas de KPI con el último dato."""
    def fmt(val):
        if val is None or pd.isna(val):
            return "N/A"
        return f"{int(val / 1000):,}K"

    def delta_badge(current, previous):
        if current is None or previous is None or pd.isna(current) or pd.isna(previous):
            return ""
        diff = current - previous
        color = "success" if diff >= 0 else "danger"
        sign = "+" if diff >= 0 else ""
        return dbc.Badge(f"{sign}{int(diff / 1000):,}K", color=color, className="ms-2")

    mm_net = (last.get('m_money_long', 0) or 0) - (last.get('m_money_short', 0) or 0)
    mm_net_prev = (prev.get('m_money_long', 0) or 0) - (prev.get('m_money_short', 0) or 0)
    pm_net = (last.get('prod_merc_long', 0) or 0) - (last.get('prod_merc_short', 0) or 0)
    pm_net_prev = (prev.get('prod_merc_long', 0) or 0) - (prev.get('prod_merc_short', 0) or 0)

    cards_data = [
        ("Open Interest",         fmt(last.get('open_interest')),     delta_badge(last.get('open_interest'), prev.get('open_interest')),   "info"),
        ("Managed Money Net",     fmt(mm_net),                        delta_badge(mm_net, mm_net_prev),                                    "primary"),
        ("Producer/Merchant Net", fmt(pm_net),                        delta_badge(pm_net, pm_net_prev),                                    "warning"),
        ("Fecha del reporte",     str(last.get('date', 'N/A')),       "",                                                                  "secondary"),
    ]

    return [
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.P(label, className="text-muted small mb-1"),
                    html.H5([value, badge], className=f"text-{color} mb-0"),
                ])
            ], className=f"border-{color}")
        ], width=3)
        for label, value, badge, color in cards_data
    ]


def _no_data_kpis():
    return [
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.P("Sin datos", className="text-muted"),
                ])
            ])
        ], width=3)
        for _ in range(4)
    ]