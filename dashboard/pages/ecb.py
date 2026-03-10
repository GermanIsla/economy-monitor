# dashboard/pages/ecb.py

import dash
from dash import html, dcc, callback, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import select
from db.engine import get_session
from db.models.ecb import ECBMarketIndicator
from dashboard.components.charts import apply_standard_layout, empty_figure

dash.register_page(__name__, path="/ecb", name="BCE", title="Economy Monitor | BCE")

TENOR_LABELS = {
    'ov': 'Overnight', 'tn': 'Tomorrow/Next', 'sn': 'Spot/Next',
    '1w': '1 Semana', '1m': '1 Mes', '3m': '3 Meses', '12m': '12 Meses'
}
COUNTRY_CODES = {'de', 'fr', 'it', 'es'}

PERIOD_OPTIONS = [
    {"label": "3 meses",  "value": 90},
    {"label": "6 meses",  "value": 180},
    {"label": "1 año",    "value": 365},
    {"label": "2 años",   "value": 730},
    {"label": "Todo",     "value": 0},
]


def _load_all_ecb(days: int = 0) -> pd.DataFrame:
    with get_session() as session:
        stmt = select(ECBMarketIndicator).order_by(ECBMarketIndicator.date.asc())
        results = session.execute(stmt).scalars().all()
        if not results:
            return pd.DataFrame()

        df = pd.DataFrame([r.__dict__ for r in results])

        def categorize(sid):
            if 'unsec_whls' in sid: return 'wholesale'
            if 'unsec_intb' in sid: return 'interbank'
            if 'sec_whls'   in sid: return 'secured'
            return 'other'

        def get_operation(sid):
            if '_le_' in sid: return 'lending'
            if '_bo_' in sid: return 'borrowing'
            return 'other'

        df['operation'] = df['series_id'].apply(get_operation)

        df['sector'] = df['series_id'].apply(categorize)

        def get_tenor(sid):
            parts = sid.split('_')
            # Si termina en código de país, el tenor es el penúltimo segmento
            return parts[-2] if parts[-1] in COUNTRY_CODES else parts[-1]

        df['tenor']   = df['series_id'].apply(get_tenor)
        df['country'] = df['series_id'].apply(
            lambda x: x.split('_')[-1].upper() if x.split('_')[-1] in COUNTRY_CODES else 'EZ'
        )

        # Distinguir series de volumen vs series de tipos de interés
        def is_rate(sid):
            return sid.endswith('_wr') or sid.startswith('ecb_')

        df['series_type'] = df['series_id'].apply(
            lambda x: 'rate' if is_rate(x) else 'volume'
        )

        # Filtro de periodo aplicado aquí, antes de devolver
        if days > 0:
            cutoff = datetime.now().date() - timedelta(days=days)
            df = df[df['date'] >= cutoff]

        return df


# --------------------------------------------------------------------------- #
# LAYOUT
# --------------------------------------------------------------------------- #
layout = dbc.Container([
    html.H2("Banco Central Europeo: Análisis de Liquidez (MMSR)", className="mb-1"),
    html.P(
        "Datos de Money Market Statistical Reporting (MMSR). "
        "Volúmenes en millones de euros.",
        className="text-muted mb-3"
    ),
    html.Hr(),

    # --- Filtro de periodo ---
    dbc.Row([
        dbc.Col([
            html.Label("Periodo:", className="fw-bold"),
            dcc.Dropdown(
                id="ecb-period-filter",
                options=PERIOD_OPTIONS,
                value=365,
                clearable=False,
            ),
        ], width=3),
    ], className="mb-4"),

    # --- KPIs ---
    html.Div(id="ecb-kpi-row", className="mb-4"),

    dbc.Tabs([
        # --- PESTAÑA 1: EVOLUCIÓN TEMPORAL ---
        dbc.Tab(label="Evolución de Temporalidades", children=[
            dbc.Row([
                dbc.Col([
                    html.H5("Indicador de Confianza: Secured vs Unsecured (Total)", className="mt-4"),
                    dbc.Card(dbc.CardBody(dcc.Graph(id="ecb-trust-comparison-chart")))
                ], width=12)
            ]),
            dbc.Row([
                dbc.Col([
                    html.H5("Ratio de Estrés Interbancario", className="mt-4"),
                    # NUEVO: reemplaza al "Wholesale 1M vs 1W gap" que era redundante.
                    # Mide qué fracción del volumen total necesita colateral (secured).
                    # Un ratio alto = bancos desconfían entre sí → indicador de estrés.
                    dbc.Card(dbc.CardBody(dcc.Graph(id="ecb-stress-ratio-chart")))
                ], width=12)
            ]),
            dbc.Row([
                dbc.Col([
                    html.H5("Wholesale Borrowing por Plazo", className="mt-4"),
                    dbc.Card(dbc.CardBody(dcc.Graph(id="ecb-line-wholesale")))
                ], width=6),
                dbc.Col([
                    html.H5("Interbank Borrowing por Plazo", className="mt-4"),
                    dbc.Card(dbc.CardBody(dcc.Graph(id="ecb-line-interbank")))
                ], width=6),
            ]),
            dbc.Row([
                dbc.Col([
                    html.H5("Wholesale vs Interbank Gap (1 Mes)", className="mt-4"),
                    dbc.Card(dbc.CardBody(dcc.Graph(id="ecb-gap-chart")))
                ], width=12)
            ]),
        ]),

        # --- PESTAÑA 2: MAPA DE CALOR Y CURVA ---
        dbc.Tab(label="Estructura y Heatmap", children=[
            dbc.Row([
                dbc.Col([
                    html.H5("Heatmap de Liquidez: Volumen por Plazo", className="mt-4"),
                    dbc.Card(dbc.CardBody(dcc.Graph(id="ecb-heatmap")))
                ], width=7),
                dbc.Col([
                    html.H5("Curva de Liquidez (Último día disponible)", className="mt-4"),
                    dbc.Card(dbc.CardBody(dcc.Graph(id="ecb-term-structure")))
                ], width=5),
            ]),
            dbc.Row([
                dbc.Col([
                    html.H5("Volumen Repo Overnight por País (Secured Lending)", className="mt-4"),
                    html.P([
                        "Barras apiladas: volumen lending overnight secured por mercado nacional. "
                        "Línea naranja: spread Repo Lending WR − DFR. ",
                        html.Strong("Cuando las barras de Alemania se reducen y el spread cae"),
                        ", es señal de escasez de colateral alemán (los bonos Bund son los más demandados)."
                    ], className="text-muted small"),
                    dbc.Card(dbc.CardBody(dcc.Graph(id="ecb-country-breakdown")))
                ], width=12)
            ]),
            dbc.Row([
                dbc.Col([
                    html.H5("Borrowing Repo Overnight por País (Secured)", className="mt-4"),
                    html.P([
                        "Volumen de borrowing overnight secured por país: el banco ",
                        html.Strong("recibe dinero y entrega el bono"), ". "
                        "Refleja qué mercados nacionales necesitan financiación. "
                        "Comparar con el gráfico de Lending arriba para identificar "
                        "flujos netos de liquidez entre países."
                    ], className="text-muted small"),
                    dbc.Card(dbc.CardBody(dcc.Graph(id="ecb-country-borrowing")))
                ], width=12)
            ]),

            dbc.Row([
                dbc.Col([
                    html.H5("Ratio Lending / Borrowing por País", className="mt-4"),
                    html.P([
                        "Ratio > 1 (zona verde): Se utilizan los bonos para proveer liquidez al mercado",
                        "Ratio < 1 (zona roja): Se utilizan los bonos para recibir liquidez o absorve los programas del BCE "
                        "Si el ratio de alemania es >1 y los demás <, puede indicar que la banca en la sombra necesita liquidez y los bancos piden activos seguros como contrapartida."
                    ], className="text-muted small"),
                    dbc.Card(dbc.CardBody(dcc.Graph(id="ecb-country-ratio")))
                ], width=12)
            ]),
        ]),
        # --- PESTAÑA 3: FLUJO DE CAPITAL Y TIPOS ---
        dbc.Tab(label="Flujo de Capital y Tipos", children=[

            # Texto introductorio
            dbc.Alert([
                html.H6("¿Qué muestra esta sección?", className="alert-heading"),
                html.P([
                    "Comparamos el volumen de operaciones repo overnight (préstamos garantizados con bonos) "
                    "en sus dos direcciones: ", html.Strong("Lending"), " (el banco presta dinero y recibe el bono) "
                    "y ", html.Strong("Borrowing"), " (el banco recibe dinero y entrega el bono). "
                    "Cruzando volúmenes con los tipos de interés ponderados, podemos detectar dos fenómenos distintos:"
                ]),
                html.Ul([
                    html.Li([html.Strong("Escasez de colateral: "),
                             "si Lending sube pero los tipos caen por debajo del DFR, los bancos están prestando "
                             "dinero casi gratis para conseguir bonos — los necesitan urgentemente."]),
                    html.Li([html.Strong("Fuga de liquidez: "),
                             "si Lending supera ampliamente a Borrowing, la banca europea está enviando "
                             "liquidez neta al exterior o a la banca en la sombra (shadow banking)."]),
                ])
            ], color="dark", className="mt-3 mb-4"),

            # --- Gráfico 1: Volumen Lending vs Borrowing ---
            dbc.Row([
                dbc.Col([
                    html.H5("Lending vs Borrowing Secured Overnight (Wholesale)", className="mt-2"),
                    html.P(
                        "Área verde = Lending (el banco envía dinero, recibe bono). "
                        "Área azul = Borrowing (el banco recibe dinero, entrega bono). "
                        "Cuando verde > azul, el sector es proveedor neto de liquidez.",
                        className="text-muted small"
                    ),
                    dbc.Card(dbc.CardBody(dcc.Graph(id="ecb-lending-borrowing-vol")))
                ], width=12)
            ]),

            # --- Gráfico 2: Ratio Lending/Borrowing ---
            dbc.Row([
                dbc.Col([
                    html.H5("Ratio Lending / Borrowing (Secured Overnight)", className="mt-4"),
                    html.P([
                        "Línea de referencia en 1.0 = equilibrio. ",
                        html.Strong("Ratio > 1:"), " el sector bancario es proveedor neto de liquidez al mercado. ",
                        html.Strong("Ratio < 1:"), " el sector tiene necesidad neta de financiación o absorbe "
                        "liquidez de los programas del BCE (TLTROs, etc.)."
                    ], className="text-muted small"),
                    dbc.Card(dbc.CardBody(dcc.Graph(id="ecb-lending-borrowing-ratio")))
                ], width=12)
            ]),

            # --- Gráficos 3 y 4: Tipos de interés ---
            dbc.Row([
                dbc.Col([
                    html.H5("Tipos de Interés Repo Overnight vs DFR", className="mt-4"),
                    html.P([
                        "Cuando el tipo repo (WR) cae ", html.Strong("por debajo del DFR"), " (línea roja), "
                        "es señal de escasez de colateral: los bancos aceptan tipos negativos con tal de "
                        "obtener los bonos."
                    ], className="text-muted small"),
                    dbc.Card(dbc.CardBody(dcc.Graph(id="ecb-repo-rates-vs-dfr")))
                ], width=7),
                dbc.Col([
                    html.H5("Spread Repo − DFR", className="mt-4"),
                    html.P([
                        "Diferencia entre el tipo repo overnight y el DFR del BCE. ",
                        html.Strong("Zona roja (negativa): "), "escasez activa de colateral en el mercado."
                    ], className="text-muted small"),
                    dbc.Card(dbc.CardBody(dcc.Graph(id="ecb-repo-dfr-spread")))
                ], width=5),
            ]),
            # --- €STR vs DFR vs Repo WR ---
            dbc.Row([
                dbc.Col([
                    html.H5("€STR vs DFR vs Repo Rate Overnight", className="mt-4"),
                    html.P([
                        "Los tres tipos overnight de referencia. ",
                        html.Strong("€STR"), " (blanco) es la media ponderada de las operaciones "
                        "de depósito interbancario overnight — el sucesor del EONIA. ",
                        "En condiciones normales €STR ≈ DFR. Si se separan, indica tensión "
                        "en el mercado de financiación a muy corto plazo."
                    ], className="text-muted small"),
                    dbc.Card(dbc.CardBody(dcc.Graph(id="ecb-estr-vs-dfr")))
                ], width=12)
            ]),

            # --- Window Dressing ---
            dbc.Row([
                dbc.Col([
                    html.H5("Detector de Window Dressing (Fin de Trimestre)", className="mt-4"),
                    html.P([
                        "Volumen total de repos overnight. Las ",
                        html.Strong("bandas rojas verticales"), " marcan el último día hábil "
                        "de cada trimestre (mar, jun, sep, dic). Picos de volumen coincidiendo "
                        "con esas bandas indican ", html.Strong("window dressing"), ": los bancos "
                        "captan bonos HQLA justo antes de la foto del regulador para mejorar su LCR."
                    ], className="text-muted small"),
                    dbc.Card(dbc.CardBody(dcc.Graph(id="ecb-window-dressing")))
                ], width=12)
            ]),
        ]),

    ])
], fluid=True)


# --------------------------------------------------------------------------- #
# CALLBACKS
# --------------------------------------------------------------------------- #

@callback(
    Output("ecb-kpi-row", "children"),
    Input("ecb-period-filter", "value"),
)
def update_kpis(days):
    """Tarjetas KPI: volumen total, ratio de estrés, tenor dominante."""
    df = _load_all_ecb(days)
    if df.empty:
        return html.P("Sin datos disponibles.", className="text-muted")

    df_vol = df[df['series_type'] == 'volume']
    if df_vol.empty:
        return html.P("Sin datos disponibles.", className="text-muted")
    latest = df_vol['date'].max()
    df_last = df_vol[df_vol['date'] == latest]

    vol_total   = df_last['value'].sum()
    vol_secured = df_last[df_last['series_id'].str.contains('sec_whls') & 
                          ~df_last['series_id'].str.endswith('_wr')]['value'].sum()
    vol_unsec   = df_last[df_last['series_id'].str.contains('unsec_') & 
                          ~df_last['series_id'].str.endswith('_wr')]['value'].sum()
    stress_ratio = (vol_secured / (vol_secured + vol_unsec) * 100) if (vol_secured + vol_unsec) > 0 else 0

    tenor_dom = (
        df_last[df_last['sector'] == 'wholesale']
        .groupby('tenor')['value'].sum()
        .idxmax()
        if not df_last[df_last['sector'] == 'wholesale'].empty
        else "N/A"
    )
    tenor_label = TENOR_LABELS.get(tenor_dom, tenor_dom)

    def kpi_card(titulo, valor, subtitulo, color="primary"):
        return dbc.Col(dbc.Card([
            dbc.CardBody([
                html.P(titulo, className="text-muted small mb-1"),
                html.H4(valor, className=f"text-{color} fw-bold mb-0"),
                html.P(subtitulo, className="text-muted small mt-1 mb-0"),
            ])
        ], className=f"border-{color}"), width=4)

    # Color del ratio de estrés: verde < 30%, amarillo < 50%, rojo ≥ 50%
    ratio_color = "success" if stress_ratio < 30 else ("warning" if stress_ratio < 50 else "danger")

    return dbc.Row([
        kpi_card(
            "Volumen Total (último día)",
            f"{vol_total:,.0f} M€",
            f"Fecha: {latest}",
        ),
        kpi_card(
            "Ratio de Estrés (Secured / Total)",
            f"{stress_ratio:.1f}%",
            "↑ más alto = menor confianza interbancaria",
            color=ratio_color,
        ),
        kpi_card(
            "Tenor Dominante (Wholesale)",
            tenor_label,
            "Mayor volumen en el último día disponible",
            color="info",
        ),
    ])


@callback(
    Output("ecb-line-wholesale",        "figure"),
    Output("ecb-line-interbank",        "figure"),
    Output("ecb-gap-chart",             "figure"),
    Output("ecb-stress-ratio-chart",    "figure"),   # NUEVO (antes: ecb-gap-chart-1m-1w)
    Output("ecb-heatmap",               "figure"),
    Output("ecb-term-structure",        "figure"),
    Output("ecb-trust-comparison-chart","figure"),
    Output("ecb-lending-borrowing-vol",   "figure"),
    Output("ecb-lending-borrowing-ratio", "figure"),
    Output("ecb-repo-rates-vs-dfr",       "figure"),
    Output("ecb-repo-dfr-spread",         "figure"),
    Output("ecb-country-breakdown", "figure"),
    Output("ecb-estr-vs-dfr",      "figure"),
    Output("ecb-window-dressing",  "figure"),
    Output("ecb-country-borrowing", "figure"),
    Output("ecb-country-ratio",     "figure"),
    Input("ecb-period-filter",          "value"),    # Ahora reactivo al filtro
)
def update_all_ecb_charts(days):
    df = _load_all_ecb(days)
    if df.empty:
        return [empty_figure()] * 16

    # Separar volúmenes de tipos de interés
    df_vol  = df[df['series_type'] == 'volume']
    df_rate = df[df['series_type'] == 'rate']

    if df_vol.empty:
        return [empty_figure()] * 16

    # --- Gráfico de confianza: Secured vs Unsecured apilado ---
    # Usar .copy() para evitar SettingWithCopyWarning
    df_trust = df_vol.copy()
    df_trust['trust_category'] = df_trust['sector'].apply(
        lambda x: 'Secured' if x == 'secured' else 'Unsecured'
    )
    trust_df = df_trust.pivot_table(
        index='date', columns='trust_category', values='value', aggfunc='sum'
    ).fillna(0).reset_index()

    fig_trust = go.Figure()
    if 'Unsecured' in trust_df.columns:
        fig_trust.add_trace(go.Scatter(
            x=trust_df['date'], y=trust_df['Unsecured'],
            name='Mercado sin Garantía (Confianza)',
            fill='tozeroy', opacity=0.5,
            line=dict(color='#00cc96')
        ))
    if 'Secured' in trust_df.columns:
        fig_trust.add_trace(go.Scatter(
            x=trust_df['date'], y=trust_df['Secured'],
            name='Mercado con Garantía (Seguridad)',
            fill='tozeroy', opacity=0.5,
            line=dict(color='#636efa')
        ))
    apply_standard_layout(fig_trust, "Composición del Mercado Monetario (M€)")
    fig_trust.update_layout(hovermode="x unified")

    # --- Líneas Wholesale e Interbank por tenor ---
    fig_whls = go.Figure()
    fig_intb = go.Figure()
    for tenor, label in TENOR_LABELS.items():
        # Wholesale — solo borrowing (unsecured)
        d_w = df_vol[
            (df_vol['sector'] == 'wholesale') &
            (df_vol['tenor'] == tenor) &
            (df_vol['operation'] == 'borrowing')
        ]
        if not d_w.empty:
            fig_whls.add_trace(go.Scatter(x=d_w['date'], y=d_w['value'], name=label, mode='lines'))

        # Interbank — solo borrowing
        d_i = df_vol[
            (df_vol['sector'] == 'interbank') &
            (df_vol['tenor'] == tenor) &
            (df_vol['operation'] == 'borrowing')
        ]
        if not d_i.empty:
            fig_intb.add_trace(go.Scatter(x=d_i['date'], y=d_i['value'], name=label, mode='lines'))
    apply_standard_layout(fig_whls, "Wholesale Tenors (M€)")
    apply_standard_layout(fig_intb, "Interbank Tenors (M€)")

    # --- Gap Wholesale vs Interbank a 1 Mes ---
    fig_gap = go.Figure()
    t_1m_w = df[(df['sector'] == 'wholesale') & (df['tenor'] == '1m')]
    t_1m_i = df[(df['sector'] == 'interbank') & (df['tenor'] == '1m')]
    fig_gap.add_trace(go.Scatter(x=t_1m_w['date'], y=t_1m_w['value'], name="Wholesale 1M", fill='tonexty'))
    fig_gap.add_trace(go.Scatter(x=t_1m_i['date'], y=t_1m_i['value'], name="Interbank 1M", fill='tozeroy'))
    apply_standard_layout(fig_gap, "Gap de Financiación a 1 Mes (Wholesale vs Interbank)")

    # --- NUEVO: Ratio de Estrés Interbancario ---
    # Secured / (Secured + Unsecured) como % del total diario.
    # Sube cuando los bancos exigen colateral → señal de desconfianza en el sistema.
    stress_df = df_trust.groupby(['date', 'trust_category'])['value'].sum().unstack(fill_value=0).reset_index()
    if 'Secured' in stress_df.columns and 'Unsecured' in stress_df.columns:
        total = stress_df['Secured'] + stress_df['Unsecured']
        stress_df['ratio'] = (stress_df['Secured'] / total * 100).where(total > 0)
    else:
        stress_df['ratio'] = 0

    fig_ratio = go.Figure()
    fig_ratio.add_trace(go.Scatter(
        x=stress_df['date'], y=stress_df['ratio'],
        mode='lines', fill='tozeroy',
        name='% Secured',
        line=dict(color='#ef553b', width=1.5)
    ))
    apply_standard_layout(fig_ratio, "Ratio de Estrés: Secured / Total (%)")
    fig_ratio.update_layout(
        hovermode="x unified",
        yaxis=dict(ticksuffix="%", range=[0, 100])
    )
    fig_ratio.add_hline(y=50, line_dash="dash", line_color="gray",
                        annotation_text="50% umbral", annotation_position="top right")

    # --- Heatmap de Liquidez (Wholesale) ---
    h_df = df_vol[df_vol['sector'] == 'wholesale'].pivot_table(
        index='tenor', columns='date', values='value', aggfunc='sum'
    ).fillna(0)
    order = [t for t in TENOR_LABELS.keys() if t in h_df.index]
    h_df = h_df.reindex(order)
    fig_heat = px.imshow(
        h_df,
        labels=dict(x="Fecha", y="Plazo", color="Volumen M€"),
        x=h_df.columns,
        y=[TENOR_LABELS[t] for t in h_df.index],
        color_continuous_scale="Viridis"
    )
    apply_standard_layout(fig_heat, "Concentración de Liquidez por Plazos")

    # --- Curva de Liquidez (último día disponible) ---
    latest_date = df_vol['date'].max()
    l_df = df_vol[(df_vol['date'] == latest_date) & (df_vol['sector'] == 'wholesale')]
    l_df = l_df.set_index('tenor').reindex(order).reset_index()
    fig_curve = go.Figure(go.Bar(
        x=[TENOR_LABELS[t] for t in l_df['tenor']],
        y=l_df['value'],
        marker_color='rgb(55, 83, 109)'
    ))
    apply_standard_layout(fig_curve, f"Distribución de Volumen al {latest_date}")


# ------------------------------------------------------------------ #
    # FLUJO DE CAPITAL Y TIPOS
    # ------------------------------------------------------------------ #

    # Extraer series concretas por ID
    def get_series(sid):
        return df[df['series_id'] == sid].set_index('date')['value']

    vol_le = get_series('mmsr_sec_whls_le_ov')   # Lending overnight vol
    vol_bo = get_series('mmsr_sec_whls_bo_ov')   # Borrowing overnight vol
    wr_le  = get_series('mmsr_sec_whls_le_ov_wr')# Lending WR
    wr_bo  = get_series('mmsr_sec_whls_bo_ov_wr')# Borrowing WR
    dfr    = get_series('ecb_dfr')               # Deposit Facility Rate
    estr = get_series('ecb_estr')  # Euro Short-Term Rate

    # --- Gráfico 1: Volumen Lending vs Borrowing ---
    fig_lb_vol = go.Figure()
    fig_lb_vol.add_trace(go.Scatter(
        x=vol_le.index, y=vol_le.values,
        name='Lending (envía dinero, recibe bono)',
        fill='tozeroy', opacity=0.7,
        line=dict(color='#00cc96')
    ))
    fig_lb_vol.add_trace(go.Scatter(
        x=vol_bo.index, y=vol_bo.values,
        name='Borrowing (recibe dinero, entrega bono)',
        fill='tozeroy', opacity=0.7,
        line=dict(color='#636efa')
    ))
    apply_standard_layout(fig_lb_vol, "Volumen Overnight Secured: Lending vs Borrowing (M€)")
    fig_lb_vol.update_layout(hovermode="x unified")

    # --- Gráfico 2: Ratio Lending/Borrowing ---
    idx_common = vol_le.index.intersection(vol_bo.index)
    ratio = (vol_le.reindex(idx_common) / vol_bo.reindex(idx_common).replace(0, float('nan')))

    fig_ratio_lb = go.Figure()
    fig_ratio_lb.add_trace(go.Scatter(
        x=ratio.index, y=ratio.values,
        name='Ratio Lending/Borrowing',
        mode='lines', fill='tozeroy',
        line=dict(color='#ffa15a', width=1.5)
    ))
    fig_ratio_lb.add_hline(y=1.0, line_dash="dash", line_color="white",
                           annotation_text="Equilibrio (1.0)",
                           annotation_position="top right")
    apply_standard_layout(fig_ratio_lb, "Ratio Lending / Borrowing Overnight Secured")
    fig_ratio_lb.update_layout(yaxis=dict(title="Ratio"))

    # --- Gráfico 3: Tipos Repo WR vs DFR ---
    fig_rates = go.Figure()
    if not wr_le.empty:
        fig_rates.add_trace(go.Scatter(
            x=wr_le.index, y=wr_le.values,
            name='Repo Rate — Lending (WR)', mode='lines',
            line=dict(color='#00cc96')
        ))
    if not wr_bo.empty:
        fig_rates.add_trace(go.Scatter(
            x=wr_bo.index, y=wr_bo.values,
            name='Repo Rate — Borrowing (WR)', mode='lines',
            line=dict(color='#636efa')
        ))
    if not dfr.empty:
        fig_rates.add_trace(go.Scatter(
            x=dfr.index, y=dfr.values,
            name='DFR (Tipo BCE)',
            mode='lines',
            line=dict(color='#ef553b', dash='dot', width=2)
        ))
    apply_standard_layout(fig_rates, "Tipos Overnight Secured vs DFR (%)")
    fig_rates.update_layout(hovermode="x unified", yaxis=dict(ticksuffix="%"))

    # --- Gráfico 4: Spread Repo (Lending WR) − DFR ---
    fig_spread = go.Figure()
    if not wr_le.empty and not dfr.empty:
        idx_s = wr_le.index.intersection(dfr.index)
        spread = wr_le.reindex(idx_s) - dfr.reindex(idx_s)
        colors = ['#ef553b' if v < 0 else '#00cc96' for v in spread.values]
        fig_spread.add_trace(go.Bar(
            x=spread.index, y=spread.values,
            name='Spread Lending WR − DFR',
            marker_color=colors
        ))
        fig_spread.add_hline(y=0, line_color="white", line_width=1)
    apply_standard_layout(fig_spread, "Spread Repo Lending − DFR (pp)")
    fig_spread.update_layout(yaxis=dict(ticksuffix=" pp"))


    # --- Gráfico por países ---
    COUNTRY_COLORS = {'DE': '#636efa', 'FR': '#ef553b', 'IT': '#00cc96', 'ES': '#ffa15a'}
    fig_country = go.Figure()

    country_df = df_vol[df_vol['country'] != 'EZ']  # solo series por país
    if not country_df.empty:
        for country, color in COUNTRY_COLORS.items():
            c_data = country_df[country_df['country'] == country].groupby('date')['value'].sum()
            if not c_data.empty:
                fig_country.add_trace(go.Bar(
                    x=c_data.index, y=c_data.values,
                    name=country, marker_color=color
                ))

        # Overlay: spread Repo − DFR en eje secundario
        if not wr_le.empty and not dfr.empty:
            idx_s = wr_le.index.intersection(dfr.index)
            spread_c = wr_le.reindex(idx_s) - dfr.reindex(idx_s)
            fig_country.add_trace(go.Scatter(
                x=spread_c.index, y=spread_c.values,
                name='Spread Repo−DFR (pp)',
                mode='lines',
                line=dict(color='white', dash='dot', width=1.5),
                yaxis='y2'
            ))
        fig_country.update_layout(barmode='stack')

    apply_standard_layout(fig_country, "Repos Overnight por País (M€)")
    fig_country.update_layout(
        hovermode="x unified",
        yaxis2=dict(
            title="Spread (pp)", overlaying='y', side='right',
            showgrid=False, ticksuffix=" pp", zeroline=True,
            zerolinecolor='gray'
        )
    )

    # --- €STR vs DFR vs Repo WR ---
    fig_estr = go.Figure()
    for serie, label, color, dash in [
        (estr,  '€STR',              '#ffffff', 'solid'),
        (dfr,   'DFR (Tipo BCE)',     '#ef553b', 'dot'),
        (wr_le, 'Repo Rate Lending',  '#00cc96', 'solid'),
        (wr_bo, 'Repo Rate Borrowing','#636efa', 'solid'),
    ]:
        if not serie.empty:
            fig_estr.add_trace(go.Scatter(
                x=serie.index, y=serie.values,
                name=label, mode='lines',
                line=dict(color=color, dash=dash, width=1.5)
            ))
    apply_standard_layout(fig_estr, "Tipos Overnight de Referencia (%)")
    fig_estr.update_layout(hovermode="x unified", yaxis=dict(ticksuffix="%"))

    # --- Window Dressing ---
    vol_total_daily = df_vol.groupby('date')['value'].sum().reset_index()
    fig_wd = go.Figure()
    fig_wd.add_trace(go.Scatter(
        x=vol_total_daily['date'], y=vol_total_daily['value'],
        name='Volumen Total Repos', mode='lines',
        fill='tozeroy', line=dict(color='#636efa', width=1.5)
    ))

    # Bandas fin de trimestre
    if not vol_total_daily.empty:
        date_range = pd.date_range(
            start=vol_total_daily['date'].min(),
            end=vol_total_daily['date'].max(),
            freq='QE'  # último día de cada trimestre
        )
        for qend in date_range:
            fig_wd.add_vrect(
                x0=qend - pd.Timedelta(days=4),
                x1=qend + pd.Timedelta(days=1),
                fillcolor='rgba(239,85,59,0.15)',
                line_width=0,
                annotation_text="fin Q",
                annotation_position="top left",
                annotation_font_size=10,
                annotation_font_color="gray"
            )

    apply_standard_layout(fig_wd, "Volumen Total Repos Overnight (M€)")
    fig_wd.update_layout(hovermode="x unified")

    # --- Borrowing por país ---
    fig_country_bo = go.Figure()
    country_bo_df = df_vol[
        (df_vol['country'] != 'EZ') & (df_vol['operation'] == 'borrowing')
    ]
    if not country_bo_df.empty:
        for country, color in COUNTRY_COLORS.items():
            c_data = country_bo_df[country_bo_df['country'] == country].groupby('date')['value'].sum()
            if not c_data.empty:
                fig_country_bo.add_trace(go.Bar(
                    x=c_data.index, y=c_data.values,
                    name=country, marker_color=color
                ))
        fig_country_bo.update_layout(barmode='stack')
    apply_standard_layout(fig_country_bo, "Borrowing Overnight por País (M€)")
    fig_country_bo.update_layout(hovermode="x unified")

    # --- Ratio Lending/Borrowing por país ---
    fig_country_ratio = go.Figure()
    fig_country_ratio.add_hline(
        y=1.0, line_dash="dash", line_color="gray",
        annotation_text="Equilibrio (1.0)", annotation_position="top right"
    )
    country_le_df = df_vol[
        (df_vol['country'] != 'EZ') & (df_vol['operation'] == 'lending')
    ]
    for country, color in COUNTRY_COLORS.items():
        le = country_le_df[country_le_df['country'] == country].groupby('date')['value'].sum()
        bo = country_bo_df[country_bo_df['country'] == country].groupby('date')['value'].sum() if not country_bo_df.empty else pd.Series(dtype=float)
        if not le.empty and not bo.empty:
            idx = le.index.intersection(bo.index)
            ratio_c = le.reindex(idx) / bo.reindex(idx).replace(0, float('nan'))
            fig_country_ratio.add_trace(go.Scatter(
                x=ratio_c.index, y=ratio_c.values,
                name=country, mode='lines',
                line=dict(color=color, width=1.5)
            ))
    apply_standard_layout(fig_country_ratio, "Ratio Lending / Borrowing por País")
    fig_country_ratio.update_layout(
        hovermode="x unified",
        yaxis=dict(title="Ratio", zeroline=True)
    )

    return (fig_whls, fig_intb, fig_gap, fig_ratio, fig_heat, fig_curve, fig_trust,
            fig_lb_vol, fig_ratio_lb, fig_rates, fig_spread, fig_country,
            fig_estr, fig_wd, fig_country_bo, fig_country_ratio)