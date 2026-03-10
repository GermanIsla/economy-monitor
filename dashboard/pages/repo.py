# dashboard/pages/repo.py
# Página completa de visualización del mercado de Repo Tri-Party
# Incluye: volumen por tipo, calidad, riesgo, liquidez GCF, estructura TPR/GCF,
#          desglose overnight/term, y desglose granular por CUSIP

import dash
from dash import html, dcc, callback, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import select
from db.engine import get_session
from db.models.repo import RepoOperation
from db.models.gcf_repo import GCFRepoTotal, RepoMarketSplit, GCFRepoAssetClass, GCFRepoCUSIP
from dashboard.components.cards import kpi_card
from dashboard.components.charts import empty_figure, CHART_LAYOUT

dash.register_page(__name__, path="/repo", name="Repo", title="Economy Monitor | Repo")

# ============================================================
# Clasificaciones de colateral
# ============================================================
COLATERAL_EXTERNO = [
    'US Treasuries Strips', 'US Treasuries excluding Strips',
    'Agency CMOs', 'Agency Debentures & Strips', 'Agency MBS', 'Municipality Debt'
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
    'Corporates Investment Grade', 'International Securities',
    'Money Market', 'Municipality Debt'
]
CALIDAD_BAJA = ['ABS Non Investment Grade', 'CMO Private Label Non Investment Grade', 'Corporates Non Investment Grade']
CALIDAD_BAJISIMA = ['CDOs', 'Equities', 'Whole Loans', 'Other']

COLORS_QUALITY = {
    'Calidad Altísima': '#3b82f6', 'Calidad Media': '#22c55e',
    'Calidad Media-Baja': '#eab308', 'Calidad Baja': '#f97316', 'Calidad Bajísima': '#ef4444',
}
QUALITY_ORDER = ['Calidad Altísima', 'Calidad Media', 'Calidad Media-Baja', 'Calidad Baja', 'Calidad Bajísima']

# ============================================================
# Textos explicativos
# ============================================================
EXPLANATIONS = {
    'main': """
**¿Qué es el mercado de Repo Tri-Party?** Un repo (repurchase agreement) es un préstamo a corto plazo
donde una parte vende valores a otra y se compromete a recomprarlos más tarde a un precio ligeramente mayor.
El "tri-party" significa que un banco intermediario (clearing bank) gestiona el colateral y la liquidación.
Es uno de los mercados más grandes del mundo — mueve billones de dólares diarios — y es crucial para la
liquidez del sistema financiero.
""",

    'origin': """
- **Colateral Externo** = deuda pública y de agencias gubernamentales (Treasuries, Agency MBS, etc.).
Es el colateral más seguro y líquido. 
- **Colateral Interno** = deuda privada, corporativa y estructurada
(ABS, CDOs, Equities, etc.). Más arriesgado pero con mejores rendimientos.
Cuando el colateral interno crece respecto al externo, indica mayor apetito por riesgo en el mercado.

""",

    'quality': """
**Calidad Altísima**: Bonos del Tesoro USA — el activo más seguro del mundo.
**Calidad Media**: Deuda de agencias gubernamentales (Fannie Mae, Freddie Mac, Ginnie Mae).
**Calidad Media-Baja**: ABS investment grade, deuda corporativa IG, deuda municipal, money market.
**Calidad Baja**: ABS e hipotecas privadas de grado especulativo (non-investment grade).
**Calidad Bajísima**: CDOs, Equities, préstamos completos (whole loans) — el colateral más arriesgado.
""",

    'risk': """
Este análisis muestra qué proporción del mercado de repo está respaldada por colateral de calidad
inferior a "media". Es un **indicador de riesgo sistémico**: cuando este porcentaje sube, significa que
se está usando más deuda de baja calidad como garantía, lo que puede amplificar las pérdidas en una crisis.
Durante la crisis de 2008, el colapso de este tipo de colateral fue uno de los detonantes del pánico.
""",

    'equities': """
**Equities como colateral** incluye acciones, ETFs, ADRs, fondos mutuos, warrants y bonos convertibles.
Es el colateral más volátil del mercado de repo. Su volumen es un indicador de cuánto apalancamiento
se está usando en el mercado de valores — cuando sube, los dealers están pidiendo más prestado usando
sus carteras de acciones como garantía, lo que aumenta el riesgo ante caídas del mercado.
""",

    'gcf_liquidity': """

Este es el análisis de la "liquidez real" del sistema. Si el gráfico de Market Structure nos mostraba el mapa de las tuberías, este nos muestra la presión del agua que corre por ellas.
En el GCF Repo, la clave no es cuánto dinero se mueve en total, sino cuánto dinero necesita quedarse un banco al final del día después de haber operado con todos los demás.

**GCF Repo** (General Collateral Finance) es un subsistema donde los dealers intercambian colateral
genérico entre ellos, gestionado por FICC (Fixed Income Clearing Corporation).
- **Gross Securities**: Volumen bruto total de valores intercambiados. Si este número es muy alto, significa que los bancos están intercambiando muchísimos activos. Es una señal de un mercado vibrante donde es fácil encontrar contraparte para "mover" papel (colateral).
- **Net Cash Borrowed**: Efectivo neto prestado — mide la **demanda real de liquidez** entre dealers. Es la cantidad de dinero real que ha cambiado de manos después de compensar todas las operaciones de compra y venta entre dealers. **Interpretación:** Es una cifra mucho más "sincera" que el volumen bruto. Si el Net Cash sube, significa que hay bancos que tienen un déficit real de dinero y no pueden compensarlo simplemente intercambiando cromos con otros.
- **Net Securities Delivered**: Valores netos entregados para cumplir las obligaciones. **¿Qué nos dice?:** Mide cuánto "papel" ha tenido que sacrificar el sistema para conseguir el dinero. **Interpretación:** Generalmente se mueve en paralelo al Net Cash. Si ves una divergencia (por ejemplo, mucho envío de valores pero poco cash recibido), podría indicar que se está entregando colateral de peor calidad que requiere mayores garantías.

La ratio **Net Cash / Gross** indica qué porcentaje del volumen es demanda real vs intermediación pura.
Si sube bruscamente, puede indicar **estrés de liquidez** en el sistema.
- Ratio Baja (Intermediación eficiente): La mayoría de las operaciones se cancelan entre sí. Los bancos actúan como intermediarios, moviendo dinero de un lado a otro sin quedarse con mucho. Las tuberías están limpias y el sistema es fluido.
- Ratio Alta (Estrés de Liquidez): Si la ratio sube bruscamente, significa que el sistema ha perdido su capacidad de compensación. Los bancos ya no están "jugando" entre ellos; están desesperados por conseguir efectivo neto.

Para entender estos datos, primero debemos entender el concepto de Netting (Compensación). En un mercado de dealers, el Banco A puede prestarle 100€ al Banco B, y el Banco B prestarle 90€ al Banco A. El volumen bruto es 190€, pero la realidad es que solo han "viajado" 10€ netos.

**Implicaciones para el Analista**
- Atasco en el sistema: Un aumento en el Net Cash Borrowed sin un aumento proporcional en el Gross sugiere que hay unos pocos bancos con problemas serios de liquidez que están absorbiendo todo el dinero disponible del mercado inter-dealer.
- Fragilidad ante Shocks: Cuando la demanda neta de efectivo es muy alta, el sistema se vuelve frágil. Si un banco grande decide dejar de prestar ese "Net Cash" un viernes por la tarde, el lunes podríamos tener una crisis de liquidez (como ocurrió en la crisis de los repos de 2019).
- Uso de Colateral: El desglose por tipos de activos (Asset Classes) nos dirá si ese efectivo neto se está consiguiendo entregando Treasuries (fácil y barato) o si están teniendo que recurrir a entregar MBS o TIPs (más caro y difícil).

La ratio **Net Securities Delivered / Net Cash Borrowed** mide el **coste en papel del dinero conseguido**.
Responde a la pregunta: ¿cuántos valores tiene que entregar el sistema para obtener 1 unidad de efectivo neto?
- **Ratio baja (< 1x)**: El sistema obtiene más cash del que entrega en valores. Alta eficiencia, colateral de calidad.
- **Ratio alta (> 1x o en aumento)**: Hay que sacrificar cada vez más papel para conseguir el mismo dinero — señal de que se está usando colateral de menor calidad, con haircuts más altos, o que la demanda de efectivo supera la oferta.
- **Divergencia con Net Cash/Gross**: Si esta ratio sube mientras la de Net Cash/Gross se mantiene estable, indica deterioro de la calidad del colateral, no necesariamente escasez de liquidez.
""",

    'market_structure': """
- **Tri-Party puro (TPR)** = repos donde el colateral se gestiona a través de un clearing bank (BNY Mellon).
Los participantes son dealers, fondos monetarios, y otros inversores institucionales.
- **GCF Repo** = un subconjunto especializado donde los dealers intercambian colateral entre sí.
Funciona como un mercado "al por mayor" dentro del mercado de repo.
- **Agency MBS (Mortgage-Backed Securities)** = Son bonos respaldados por pools de hipotecas residenciales o comerciales. Un volumen alto de Agency MBS indica un mercado hipotecario activo y que los dealers están cómodos financiando activos que rinden un poco más que el Tesoro a cambio de un riesgo marginalmente mayor.
- **Agency (Other than MBS) - Deuda de Agencia "Pura"** = Es deuda que las agencias (Fannie, Freddie, Federal Home Loan Banks, etc.) emiten para financiar sus propias operaciones diarias, no para empaquetar hipotecas. Son bonos "normales" emitidos por estas entidades. Son un termómetro de la salud financiera de las instituciones que sostienen el sistema de vivienda de EE.UU.
- **Treasury** = Es deuda emitida directamente por el Departamento del Tesoro de EE.UU. Si el volumen de Treasuries en el Repo sube, el mercado está en modo defensivo. Es el activo al que todos corren cuando hay pánico en la bolsa o incertidumbre geopolítica.


Si el GCF crece más rápido que el TPR, indica que los dealers están redistribuyendo más colateral entre
ellos — señal de que hay **desequilibrios** en la posesión de ciertos tipos de activos.

Para entender este gráfico, hay que visualizar el mercado como un sistema de dos niveles: el dinero que entra de "fuera" (TPR) y el dinero que se mueven los bancos "dentro" (GCF).

El Tri-Party Repo es la puerta de entrada de liquidez al sistema bancario.
- ¿Quién participa?: Por un lado, los que tienen mucho efectivo sobrante (Fondos del Mercado Monetario o MMF, fondos de pensiones, aseguradoras). Por el otro, los Dealers (grandes bancos como JP Morgan o Goldman Sachs) que necesitan ese dinero para financiar sus operaciones.
- El "Tercero" (Tri-Party): Se llama así porque hay un banco agente (principalmente BNY Mellon) que se encarga de que el intercambio sea seguro: custodia el colateral, valora los activos y mueve el efectivo.
- Función: Es la fuente primaria de financiación. Si el volumen de TPR sube, significa que hay mucha liquidez "fresca" entrando al sistema desde los inversores institucionales.

El GCF Repo es un mercado cerrado y anónimo exclusivo para dealers que pertenecen a la FICC (Fixed Income Clearing Corporation).
- ¿Qué es?: Es un "sub-mercado" donde los bancos se prestan dinero entre ellos usando cestas de activos (colateral genérico) en lugar de bonos específicos.
- Anonimato: Aquí los bancos no saben con quién están operando; la FICC actúa como la contraparte central, garantizando que todos cobren.
- Función: Sirve para redistribuir la liquidez. Si un banco consiguió mucho dinero en el TPR pero otro banco se quedó corto, se lo prestan en el GCF.

**Implicaciones**
- Eficiencia en el Reparto: Si el volumen de GCF es una fracción pequeña y estable del TPR, el mercado es eficiente.
- Concentración de Riesgo: Un GCF muy alto comparado con el TPR sugiere que el sistema depende demasiado del intercambio interno entre bancos. Si uno de esos bancos falla, el efecto dominó es mucho más rápido.
- Métrica de Intermediación: El volumen neto de efectivo en GCF (Net Cash Borrowed) comparado con el volumen bruto de valores (Gross Securities) te indica cuánta de esa actividad es "necesidad real de dinero" vs. simplemente mover papeles para cuadrar cuentas.
""",

    'overnight_term': """
- **Overnight** = préstamos a un día. Se devuelven al día siguiente.
- **Term** = préstamos a plazo (varios días, semanas o meses).
- **Agency MBS (Mortgage-Backed Securities)** = Son bonos respaldados por pools de hipotecas residenciales o comerciales. Un volumen alto de Agency MBS indica un mercado hipotecario activo y que los dealers están cómodos financiando activos que rinden un poco más que el Tesoro a cambio de un riesgo marginalmente mayor.
- **Agency (Other than MBS) - Deuda de Agencia "Pura"** = Es deuda que las agencias (Fannie, Freddie, Federal Home Loan Banks, etc.) emiten para financiar sus propias operaciones diarias, no para empaquetar hipotecas. Son bonos "normales" emitidos por estas entidades. Son un termómetro de la salud financiera de las instituciones que sostienen el sistema de vivienda de EE.UU.
- **Treasury** = Es deuda emitida directamente por el Departamento del Tesoro de EE.UU. Si el volumen de Treasuries en el Repo sube, el mercado está en modo defensivo. Es el activo al que todos corren cuando hay pánico en la bolsa o incertidumbre geopolítica.

La proporción overnight/term es reveladora:
- Más overnight → los participantes **no quieren comprometerse** a plazos largos (incertidumbre).
- Más term → los participantes se sienten **cómodos** prestando a mayor plazo (confianza).
Un giro súbito hacia overnight puede anticipar estrés en el mercado.

La Dimensión Temporal: Overnight vs. Term

En el mercado Repo, el tiempo es el factor que mide el riesgo de contraparte. No es lo mismo prestar 1.000 millones de dólares para que te los devuelvan mañana, que prestarlos para que te los devuelvan en 30 días.

1. Definición de los Componentes
- Overnight (O/N): Son préstamos con vencimiento a 24 horas. Es la forma más pura de liquidez inmediata. Los participantes usan el "Overnight" para cuadrar sus balances al cierre del día y cumplir con las regulaciones.
- Term (Plazo): Son contratos que duran desde 2 días hasta varios meses. Representan la financiación estructural del sistema. Aquí es donde los bancos financian sus carteras de bonos a largo plazo.

2. Cómo interpretar la Proporción (La Señal)
Para entender este gráfico, debes mirar la relación entre ambos, no solo el volumen total:
- Entorno de Confianza (Dominio del Term): Cuando el porcentaje de operaciones a plazo (Term) es alto o estable, significa que los prestamistas (quienes tienen el efectivo) no temen que el prestatario quiebre en las próximas semanas. Hay una visibilidad clara sobre los tipos de interés de la Fed y el sistema fluye con calma.
- Entorno de Incertidumbre o Estrés (Refugio en Overnight): Si ves que el volumen de Term cae y el de Overnight sube bruscamente (lo que llamamos la "overnight-ización" del mercado), es una señal de alarma. Los prestamistas dicen: "Te presto hoy porque mañana puedo recuperar mi dinero si algo explota, pero no me pidas que me comprometa contigo a un mes".

3. Los "Red Flags" (Banderas Rojas)
- Riesgo de Renovación (Roll-over Risk): Si un dealer depende excesivamente del Overnight, vive al borde del abismo. Si una mañana el mercado se asusta y nadie le presta (como ocurrió en septiembre de 2019), ese dealer entra en crisis de liquidez en cuestión de horas.
- Inversión de Expectativas: Si los tipos de interés del Repo Term empiezan a subir mucho más rápido que el Overnight, el mercado está descontando una subida de tipos de la Fed inminente o, peor aún, una escasez de colateral a futuro.

4. Implicaciones Macroeconómicas
- Transmisión de Política Monetaria: La Fed prefiere un mercado con un componente saludable de Term, ya que esto estabiliza los tipos de interés en toda la economía (hipotecas, créditos, etc.).
- Volatilidad en los Mercados: Un mercado puramente Overnight es un mercado nervioso. Cualquier noticia económica se traduce en cambios bruscos en el coste de financiación diaria, lo que acaba afectando a la volatilidad de la bolsa (S&P 500) y de los bonos.

Resumen para el analista:
- Sube Overnight / Baja Term: "Tengo miedo al futuro cercano, quiero mi dinero disponible mañana mismo". (Incertidumbre/Riesgo).
- Baja Overnight / Sube Term: "El sistema es predecible, puedo bloquear mi capital a cambio de un poco más de rentabilidad". (Confianza/Estabilidad).

""",
    'cusips': """
Desglose granular del GCF Repo por tipo específico de valor:
- **Treasury (<10Y, <30Y)**: Bonos del Tesoro por plazo de vencimiento
- **TIPs**: Treasury Inflation-Protected Securities (protección contra inflación)
- **STRIPs**: Bonos del Tesoro descompuestos en cupones individuales
- **FNMA/FHLMC Fixed Rate**: Hipotecas de Fannie Mae/Freddie Mac a tipo fijo
- **FNMA/FHLMC ARMs**: Hipotecas a tipo variable (más sensibles a tipos de interés)
- **GNMA**: Hipotecas de Ginnie Mae (respaldadas directamente por el gobierno)

Si los participantes rotan de MBS hacia Treasury, buscan **seguridad**.
Si rotan hacia ARMs o TIPs, están posicionándose para **cambios en tipos de interés o inflación**.

El GCF Repo (General Collateral Finance) es, en esencia, el mercado donde los grandes operadores (dealers) se prestan dinero entre sí de forma anónima usando garantías de alta calidad.
- **Treasury (<10Y, <30Y)**: Deuda pública de EE.UU. a corto y largo plazo.Es el "colateral rey". Si su volumen sube, el mercado busca la máxima seguridad y liquidez posible.
- **TIPs**: Treasury Inflation-Protected Securities (protección contra inflación). Si aumenta su uso en repo, indica que los participantes esperan que la inflación sea más alta de lo previsto y quieren cubrirse.
- **STRIPs**: Bonos del Tesoro descompuestos en cupones individuales. Son extremadamente sensibles a los movimientos de los tipos de interés. Se usan para apuestas muy precisas sobre la curva de tipos.
- **MBS (FNMA/FHLMC)**: Hipotecas de Fannie Mae y Freddie Mac. Son agencias respaldadas por el gobierno, pero con un toque más de riesgo que el Tesoro. Los ARMs (tipo variable) son termómetros de la volatilidad de tipos a corto plazo.
- **GNMA**: Hipotecas de Ginnie Mae (respaldadas directamente por el gobierno). Tienen garantía total del gobierno de EE.UU. Son el puente entre la seguridad del Tesoro y el mercado hipotecario.

**Lectura Estratégica:**
- **Vuelo a la calidad**: Rotación de MBS (hipotecas) hacia Treasury. El mercado tiene miedo.
- **Apetito por el riesgo**: Mayor peso de ARMs o Agency MBS frente al Tesoro.
- **Señales de alerta**: Un aumento súbito en **STRIPs** suele indicar dificultades para gestionar la duración en las carteras de los grandes bancos.
- **Alerta de Inflación**: Un aumento repentino en el volumen de TIPs como colateral suele preceder a datos de IPC moviditos o cambios en el discurso de la Fed.
- **Problemas de Duración**: Si los STRIPs o Treasury <30Y empiezan a dominar, los participantes están teniendo dificultades para financiar sus posiciones de largo plazo, lo que puede indicar tensión en la curva de tipos.

**Implicaciones Macroeconómicas:**
- **Liquidez del Sistema**: Si el volumen total de GCF Repo cae drásticamente, los dealers tienen menos capacidad de "hacer mercado". Esto suele traer más volatilidad a la bolsa y a los bonos.
- **Transmisión de la Política de la Fed**: Si la Fed sube tipos pero el mercado de Repo no reacciona o se descorrelaciona, tenemos un problema de transmisión monetaria.
- **Stress Bancario**: El GCF Repo es ciego (blind brokered). Si los tipos en este mercado suben mucho por encima de la tasa de la Fed (IOER), significa que los bancos se están guardando el dinero y no confían en el sistema.


""",
    'all': """
Vista detallada de todos los tipos de colateral individuales del mercado tri-party.
Cada línea representa una clase de activo específica. Los tipos Fedwire-eligible
(Treasuries, Agency MBS, Agency Debentures) son los más líquidos y seguros.

1. Los Activos "Estructurales" (El suelo del mercado)
Son los activos Fedwire-eligible, lo que significa que pueden moverse instantáneamente a través del sistema de liquidación de la Reserva Federal.
- Treasury Strips y Excluding Strips: Es deuda pura del gobierno. Si estas líneas dominan, el mercado es aburrido pero seguro.
- Agency Debentures & MBS: Como vimos, son el respaldo hipotecario institucional.
- Municipality Debt: Deuda de estados y ciudades. Es muy segura, pero menos líquida que los bonos del tesoro.

2. El "Crédito Privado" (Donde empieza el riesgo)
Aquí es donde los bancos usan deuda de empresas o préstamos para conseguir efectivo.
- Corporates (Investment Grade vs. Non-Investment Grade): Deuda de empresas. Si ves que la línea de Non-Investment Grade (bonos basura) sube, el mercado está aceptando mucho riesgo a cambio de rentabilidad.
- ABS (Asset-Backed Securities): Son paquetes de préstamos (de coches, tarjetas de crédito, etc.).
- CMO Private Label: A diferencia de los Agency MBS, estos no tienen respaldo del gobierno. Son hipotecas privadas "empaquetadas". Si esta línea sube, la sombra de 2008 vuelve a asomarse.

3. El Colateral "Exótico" y de Alto Riesgo
Si estas líneas crecen, la fragilidad del sistema aumenta exponencialmente:
- Equities (Acciones): Incluye acciones y ETFs. Es colateral muy volátil. Si la bolsa cae un 10%, el colateral que garantiza el préstamo también vale un 10% menos de golpe.
- CDOs (Collateralized Debt Obligations): Famosos por la crisis subprime. Son derivados complejos. Verlos en el repo hoy es raro, pero indica una ingeniería financiera agresiva.
- Whole Loans: Préstamos completos que aún no han sido "empaquetados". Son los más difíciles de vender en caso de emergencia.

**El Concepto del "Haircut"** (El margen de desconfianza)
Aunque no sea una línea de volumen, el Haircut (recorte) es lo que define cuánto vale cada línea en realidad.
    Ejemplo: Si entregas 100M$ en Treasuries, el banco te presta 98M$ (Haircut del 2%). Pero si entregas 100M$ en Equities, quizás solo te presten 85M$ (Haircut del 15%).
¿Por qué es importante en tu gráfico?
Si ves que el volumen de activos con Haircuts altos (como Equities o Corporates Non-IG) está subiendo, significa que el sistema se está apalancando con activos de baja calidad. Si el mercado cae, esos "recortes" aumentarán, obligando a los bancos a devolver el dinero de golpe (un Margin Call sistémico).

"""
}


def _explanation_box(key: str) -> dbc.Alert:
    """Genera un cuadro explicativo colapsable."""
    return dbc.Card([
        dbc.CardBody([
            html.Details([
                html.Summary(
                    html.Span(["ℹ️ ¿Cómo interpretar este gráfico?"],
                              className="fw-bold text-info"),
                ),
                dcc.Markdown(EXPLANATIONS.get(key, ''), className="mt-2 small"),
            ])
        ])
    ], className="mb-3 border-info")


# ============================================================
# Layout
# ============================================================
layout = dbc.Container([
    html.H2("Mercado de Repo Tri-Party", className="mb-1"),
    html.P("Volumen, composición, calidad y liquidez del mercado de repo.", className="text-muted mb-3"),

    _explanation_box('main'),
    html.Hr(),

    dbc.Row([
        dbc.Col([
            html.Label("Vista:", className="fw-bold"),
            dcc.Dropdown(
                id="repo-view-filter",
                options=[
                    {"label": "📊 Origen (Interno vs Externo)", "value": "origin"},
                    {"label": "🏅 Calidad del Colateral", "value": "quality"},
                    {"label": "⚠️ Análisis de Riesgo", "value": "risk"},
                    {"label": "📈 Equities (detalle)", "value": "equities"},
                    {"label": "💰 Liquidez GCF (Net Cash)", "value": "gcf_liquidity"},
                    {"label": "🏗️ Estructura TPR vs GCF", "value": "market_structure"},
                    {"label": "🌙 Overnight vs Term", "value": "overnight_term"},
                    {"label": "🔬 Desglose por CUSIP", "value": "cusips"},
                    {"label": "📋 Todos los tipos", "value": "all"},
                ],
                value="origin",
                clearable=False
            ),
        ], width=4),
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

    html.Div(id="repo-kpi-row", className="mb-4"),
    html.Div(id="repo-explanation-box", className="mb-2"),

    dbc.Row([dbc.Col([dbc.Card([dbc.CardBody([dcc.Graph(id="repo-main-chart")])])], width=12)], className="mb-4"),
    dbc.Row([dbc.Col([dbc.Card([dbc.CardBody([dcc.Graph(id="repo-secondary-chart")])])], width=12)]),
    html.Div(
        id="repo-tertiary-chart-row",
        children=[dbc.Row([dbc.Col([dbc.Card([dbc.CardBody([dcc.Graph(id="repo-tertiary-chart")])])], width=12)], className="mt-4")],
        style={'display': 'none'}
    ),
    ], fluid=True)


# ============================================================
# Helpers
# ============================================================
def _base_layout(**overrides):
    base = dict(CHART_LAYOUT)
    base.update(overrides)
    return base

def _load_repo(period_days: int) -> pd.DataFrame:
    with get_session() as session:
        stmt = select(RepoOperation).order_by(RepoOperation.date)
        if period_days > 0:
            stmt = stmt.where(RepoOperation.date >= datetime.now().date() - timedelta(days=period_days))
        results = session.execute(stmt).scalars().all()
    if not results:
        return pd.DataFrame()
    df = pd.DataFrame([{'date': r.date, 'group_name': r.group_name, 'collateral_value': r.collateral_value} for r in results])
    df['date'] = pd.to_datetime(df['date'])
    return df

def _load_gcf_total(period_days: int) -> pd.DataFrame:
    with get_session() as session:
        stmt = select(GCFRepoTotal).order_by(GCFRepoTotal.date)
        if period_days > 0:
            stmt = stmt.where(GCFRepoTotal.date >= datetime.now().date() - timedelta(days=period_days))
        results = session.execute(stmt).scalars().all()
    if not results:
        return pd.DataFrame()
    return pd.DataFrame([{'date': r.date, 'metric_type': r.metric_type, 'value': r.value} for r in results])

def _load_market_split(period_days: int) -> pd.DataFrame:
    with get_session() as session:
        stmt = select(RepoMarketSplit).order_by(RepoMarketSplit.date)
        if period_days > 0:
            stmt = stmt.where(RepoMarketSplit.date >= datetime.now().date() - timedelta(days=period_days))
        results = session.execute(stmt).scalars().all()
    if not results:
        return pd.DataFrame()
    return pd.DataFrame([{'date': r.date, 'collateral_type': r.collateral_type, 'tpr_value': r.tpr_value, 'tpr_share': r.tpr_share, 'gcf_value': r.gcf_value, 'gcf_share': r.gcf_share} for r in results])

def _load_asset_classes(period_days: int) -> pd.DataFrame:
    with get_session() as session:
        stmt = select(GCFRepoAssetClass).order_by(GCFRepoAssetClass.date)
        if period_days > 0:
            stmt = stmt.where(GCFRepoAssetClass.date >= datetime.now().date() - timedelta(days=period_days))
        results = session.execute(stmt).scalars().all()
    if not results:
        return pd.DataFrame()
    return pd.DataFrame([{'date': r.date, 'collateral_type': r.collateral_type, 'overnight': r.overnight, 'overnight_share': r.overnight_share, 'term': r.term, 'term_share': r.term_share} for r in results])

def _load_cusips(period_days: int) -> pd.DataFrame:
    with get_session() as session:
        stmt = select(GCFRepoCUSIP).order_by(GCFRepoCUSIP.date)
        if period_days > 0:
            stmt = stmt.where(GCFRepoCUSIP.date >= datetime.now().date() - timedelta(days=period_days))
        results = session.execute(stmt).scalars().all()
    if not results:
        return pd.DataFrame()
    return pd.DataFrame([{'date': r.date, 'collateral_type': r.collateral_type, 'overnight': r.overnight, 'overnight_share': r.overnight_share, 'term': r.term, 'term_share': r.term_share} for r in results])

def _classify_quality(gn):
    if gn in CALIDAD_ALTISIMA: return 'Calidad Altísima'
    if gn in CALIDAD_MEDIA: return 'Calidad Media'
    if gn in CALIDAD_MEDIA_BAJA: return 'Calidad Media-Baja'
    if gn in CALIDAD_BAJA: return 'Calidad Baja'
    if gn in CALIDAD_BAJISIMA: return 'Calidad Bajísima'
    return 'Sin Categoría'

def _classify_origin(gn):
    if gn in COLATERAL_EXTERNO: return 'Colateral Externo'
    if gn in COLATERAL_INTERNO: return 'Colateral Interno'
    return 'Sin Categoría'


# ============================================================
# Callback
# ============================================================
@callback(
    Output("repo-kpi-row", "children"),
    Output("repo-explanation-box", "children"),
    Output("repo-main-chart", "figure"),
    Output("repo-secondary-chart", "figure"),
    Output("repo-tertiary-chart", "figure"),
    Output("repo-tertiary-chart-row", "style"),
    Input("repo-view-filter", "value"),
    Input("repo-period-filter", "value"),
)
def update_repo(view, period_days):
    empty = empty_figure("Sin datos. Ejecuta: python run_pipeline.py repo")
    no_kpi = dbc.Row([dbc.Col(kpi_card("Repo", "Sin datos", icon="bi-arrow-left-right"), width=3)])
    explanation = _explanation_box(view)

    df = _load_repo(period_days)
    if df.empty and view in ['origin', 'quality', 'risk', 'equities', 'all']:
        return no_kpi, explanation, empty, empty

    # --- KPIs ---
    from utils.helpers import format_amount
    if not df.empty:
        latest = df['date'].max()
        dl = df[df['date'] == latest]
        total_vol = dl['collateral_value'].sum()
        treas = dl[dl['group_name'].isin(CALIDAD_ALTISIMA)]['collateral_value'].sum()
        eq = dl[dl['group_name'] == 'Equities']['collateral_value'].sum()
        dl_q = dl.copy()
        dl_q['q'] = dl_q['group_name'].apply(_classify_quality)
        low = dl_q[dl_q['q'].isin(['Calidad Media-Baja', 'Calidad Baja', 'Calidad Bajísima'])]['collateral_value'].sum()
        pct_low = (low / total_vol * 100) if total_vol > 0 else 0
        kpi_row = dbc.Row([
            dbc.Col(kpi_card("Volumen Total", format_amount(total_vol), icon="bi-arrow-left-right"), width=3),
            dbc.Col(kpi_card("US Treasuries", format_amount(treas), icon="bi-bank"), width=3),
            dbc.Col(kpi_card("Equities", format_amount(eq), icon="bi-graph-up-arrow"), width=3),
            dbc.Col(kpi_card("Colateral ≤ Media-Baja", f"{pct_low:.1f}%", icon="bi-exclamation-triangle"), width=3),
        ])
    else:
        kpi_row = no_kpi

    # --- Despachar a la vista ---
    dispatch = {
        'origin': lambda: _view_origin(df),
        'quality': lambda: _view_quality(df),
        'risk': lambda: _view_risk(df),
        'equities': lambda: _view_equities(df),
        'gcf_liquidity': lambda: _view_gcf_liquidity(period_days),
        'market_structure': lambda: _view_market_structure(period_days),
        'overnight_term': lambda: _view_overnight_term(period_days),
        'cusips': lambda: _view_cusips(period_days),
        'all': lambda: _view_all(df),
    }
    if view == 'gcf_liquidity':
        fig_main, fig_sec, fig_ter = dispatch.get(view, lambda: (empty, empty, empty))()
        return kpi_row, explanation, fig_main, fig_sec, fig_ter, {'display': 'block'}
    else:
        fig_main, fig_sec = dispatch.get(view, lambda: (empty, empty))()
        return kpi_row, explanation, fig_main, fig_sec, empty_figure(""), {'display': 'none'}


# ============================================================
# Vistas — Repo Operations (volume_haircut_concentration)
# ============================================================
def _view_origin(df):
    df = df.copy()
    df['origin'] = df['group_name'].apply(_classify_origin)
    g = df.groupby(['date', 'origin'])['collateral_value'].sum().unstack().fillna(0)
    colors = {'Colateral Externo': '#3b82f6', 'Colateral Interno': '#f59e0b'}
    fig1 = go.Figure()
    for c in ['Colateral Externo', 'Colateral Interno']:
        if c in g.columns:
            fig1.add_trace(go.Scatter(x=g.index, y=g[c], mode='lines', name=c, line=dict(color=colors[c], width=2), stackgroup='one'))
    fig1.update_layout(**_base_layout(title_text="Volumen por Origen del Colateral", yaxis_title="Volumen (miles de millones USD)"))

    pct = g.div(g.sum(axis=1), axis=0) * 100
    fig2 = go.Figure()
    for c in ['Colateral Externo', 'Colateral Interno']:
        if c in pct.columns:
            fig2.add_trace(go.Scatter(x=pct.index, y=pct[c], mode='lines', name=c, line=dict(color=colors[c]), stackgroup='one'))
    fig2.update_layout(**_base_layout(title_text="Proporción Interno vs Externo (%)", yaxis_title="% del Total", yaxis_range=[0, 100]))
    return fig1, fig2

def _view_quality(df):
    df = df.copy()
    df['quality'] = df['group_name'].apply(_classify_quality)
    g = df.groupby(['date', 'quality'])['collateral_value'].sum().unstack().fillna(0)
    fig1 = go.Figure()
    for q in QUALITY_ORDER:
        if q in g.columns:
            fig1.add_trace(go.Scatter(x=g.index, y=g[q], mode='lines', name=q, line=dict(color=COLORS_QUALITY.get(q), width=2)))
    fig1.update_layout(**_base_layout(title_text="Volumen por Calidad del Colateral", yaxis_title="Volumen (miles de millones USD)"))

    total = g.sum(axis=1)
    pct = g.div(total, axis=0) * 100
    fig2 = go.Figure()
    for q in QUALITY_ORDER:
        if q in pct.columns:
            fig2.add_trace(go.Scatter(x=pct.index, y=pct[q], mode='lines', name=q, line=dict(color=COLORS_QUALITY.get(q), width=1), stackgroup='one'))
    fig2.update_layout(**_base_layout(title_text="Composición por Calidad (% del Total)", yaxis_title="%", yaxis_range=[0, 100]))
    return fig1, fig2

def _view_risk(df):
    df = df.copy()
    df['quality'] = df['group_name'].apply(_classify_quality)
    g = df.groupby(['date', 'quality'])['collateral_value'].sum().unstack().fillna(0)
    total = g.sum(axis=1)
    risk_cats = ['Calidad Media-Baja', 'Calidad Baja', 'Calidad Bajísima']

    fig1 = go.Figure()
    for q in QUALITY_ORDER:
        if q in g.columns:
            fig1.add_trace(go.Scatter(x=g.index, y=g[q], mode='lines', name=q, line=dict(color=COLORS_QUALITY.get(q), width=2)))
    fig1.update_layout(**_base_layout(title_text="Volumen por Categoría de Calidad", yaxis_title="Volumen (miles de millones USD)"))

    fig2 = go.Figure()
    cols = [q for q in risk_cats if q in g.columns]
    if cols:
        total_risk = g[cols].sum(axis=1)
        pct = (total_risk / total * 100).fillna(0)
        fig2.add_trace(go.Scatter(x=pct.index, y=pct, mode='lines', name='% Colateral ≤ Media-Baja', line=dict(color='#ef4444', width=2.5), fill='tozeroy', fillcolor='rgba(239, 68, 68, 0.15)'))
        avg = pct.mean()
        fig2.add_hline(y=avg, line_width=1, line_dash="dash", line_color="rgba(255,255,255,0.4)", annotation_text=f"Media: {avg:.1f}%", annotation_position="top right", annotation_font_color="rgba(255,255,255,0.6)")
    fig2.update_layout(**_base_layout(title_text="Colateral de Riesgo (≤ Media-Baja) como % del Total", yaxis_title="% del Total", showlegend=False))
    return fig1, fig2

def _view_equities(df):
    eq = df[df['group_name'] == 'Equities'].sort_values('date')
    if eq.empty:
        e = empty_figure("Sin datos de Equities")
        return e, e
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=eq['date'], y=eq['collateral_value'], mode='lines', name='Equities', line=dict(color='#06b6d4', width=2), fill='tozeroy', fillcolor='rgba(6, 182, 212, 0.15)'))
    fig1.update_layout(**_base_layout(title_text="Volumen de Repo con Colateral de Equities", yaxis_title="Volumen (miles de millones USD)"))

    eq2 = eq.copy()
    eq2['pct'] = eq2['collateral_value'].pct_change() * 100
    colors = ['rgba(239,68,68,0.7)' if v > 0 else 'rgba(34,197,94,0.7)' for v in eq2['pct'].fillna(0)]
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(x=eq2['date'], y=eq2['pct'], marker_color=colors))
    fig2.add_hline(y=0, line_width=1, line_color="gray")
    fig2.update_layout(**_base_layout(title_text="Variación Porcentual Mensual", yaxis_title="Cambio (%)", showlegend=False))
    return fig1, fig2

def _view_all(df):
    g = df.groupby(['date', 'group_name'])['collateral_value'].sum().unstack().fillna(0)
    fig1 = go.Figure()
    for col in sorted(g.columns):
        fig1.add_trace(go.Scatter(x=g.index, y=g[col], mode='lines', name=col, line=dict(width=1.5)))
    fig1.update_layout(template='plotly_dark', title_text="Todos los Tipos de Colateral", title_x=0.5, yaxis_title="Volumen", margin={'r': 200}, legend=dict(orientation='v', yanchor='top', y=1, xanchor='left', x=1.02, font=dict(size=9)))

    f6m = g.index.max() - pd.DateOffset(months=6)
    rec = g[g.index >= f6m]
    fig2 = go.Figure()
    for col in sorted(rec.columns):
        fig2.add_trace(go.Scatter(x=rec.index, y=rec[col], mode='lines', name=col, stackgroup='one', line=dict(width=0.5)))
    fig2.update_layout(template='plotly_dark', title_text="Composición (últimos 6 meses, apilado)", title_x=0.5, yaxis_title="Volumen", margin={'r': 200}, legend=dict(orientation='v', yanchor='top', y=1, xanchor='left', x=1.02, font=dict(size=9)))
    return fig1, fig2


# ============================================================
# Vistas — GCF Repo Total
# ============================================================
def _view_gcf_liquidity(period_days):
    df = _load_gcf_total(period_days)
    if df.empty:
        e = empty_figure("Sin datos de GCF Repo Total")
        return e, e

    df['date'] = pd.to_datetime(df['date'])
    g = df.pivot_table(index='date', columns='metric_type', values='value', aggfunc='first').fillna(0)

    colors_m = {'Gross Securities': '#3b82f6', 'Net Cash Borrowed': '#ef4444', 'Net Securities Delivered': '#22c55e'}
    fig1 = go.Figure()
    for col in ['Gross Securities', 'Net Cash Borrowed', 'Net Securities Delivered']:
        if col in g.columns:
            fig1.add_trace(go.Scatter(x=g.index, y=g[col], mode='lines+markers', name=col, line=dict(color=colors_m.get(col), width=2), marker=dict(size=5)))
    fig1.update_layout(**_base_layout(title_text="GCF Repo: Volúmenes Totales", yaxis_title="Miles de millones USD"))

    fig2 = go.Figure()
    if 'Net Cash Borrowed' in g.columns and 'Gross Securities' in g.columns:
        ratio = (g['Net Cash Borrowed'] / g['Gross Securities'] * 100).fillna(0)
        fig2.add_trace(go.Scatter(x=ratio.index, y=ratio, mode='lines+markers', name='Net Cash / Gross (%)', line=dict(color='#f59e0b', width=2.5), fill='tozeroy', fillcolor='rgba(245, 158, 11, 0.12)', marker=dict(size=5)))
        avg = ratio.mean()
        fig2.add_hline(y=avg, line_dash="dash", line_color="rgba(255,255,255,0.4)", annotation_text=f"Media: {avg:.1f}%", annotation_position="top right", annotation_font_color="rgba(255,255,255,0.6)")
    fig2.update_layout(**_base_layout(title_text="Ratio de Demanda de Liquidez (Net Cash / Gross)", yaxis_title="% del Bruto", showlegend=False))

    fig3 = go.Figure()
    if 'Net Securities Delivered' in g.columns and 'Net Cash Borrowed' in g.columns:
        ratio3 = (g['Net Securities Delivered'] / g['Net Cash Borrowed']).replace([float('inf'), float('-inf')], None).fillna(0)
        fig3.add_trace(go.Scatter(
            x=ratio3.index, y=ratio3, mode='lines+markers',
            name='Net Securities / Net Cash',
            line=dict(color='#a78bfa', width=2.5),
            fill='tozeroy', fillcolor='rgba(167, 139, 250, 0.12)',
            marker=dict(size=5)
        ))
        avg3 = ratio3.mean()
        fig3.add_hline(y=avg3, line_dash="dash", line_color="rgba(255,255,255,0.4)",
                       annotation_text=f"Media: {avg3:.2f}x", annotation_position="top right",
                       annotation_font_color="rgba(255,255,255,0.6)")
    fig3.update_layout(**_base_layout(
        title_text="Coste del Colateral: Net Securities Delivered / Net Cash Borrowed",
        yaxis_title="Ratio (x veces)", showlegend=False
    ))
    return fig1, fig2, fig3


# ============================================================
# Vistas — Tri-Party vs GCF Split
# ============================================================
def _view_market_structure(period_days):
    df = _load_market_split(period_days)
    if df.empty:
        e = empty_figure("Sin datos de estructura TPR/GCF")
        return e, e

    df['date'] = pd.to_datetime(df['date'])
    colors_t = {'Treasury': '#3b82f6', 'Agency MBS': '#22c55e', 'Agency (other than MBS)': '#f59e0b'}

    fig1 = go.Figure()
    for ct in df['collateral_type'].unique():
        sub = df[df['collateral_type'] == ct].sort_values('date')
        c = colors_t.get(ct, '#888')
        if sub['tpr_value'].notna().any():
            fig1.add_trace(go.Scatter(x=sub['date'], y=pd.to_numeric(sub['tpr_value'], errors='coerce'), mode='lines', name=f'TPR: {ct}', line=dict(color=c, width=2)))
        if sub['gcf_value'].notna().any():
            fig1.add_trace(go.Scatter(x=sub['date'], y=pd.to_numeric(sub['gcf_value'], errors='coerce'), mode='lines', name=f'GCF: {ct}', line=dict(color=c, width=2, dash='dot')))
    fig1.update_layout(**_base_layout(title_text="Volumen por Segmento: Tri-Party (sólida) vs GCF (punteada)", yaxis_title="Miles de millones USD"))

    # Proporción TPR vs GCF por fecha
    tpr_total = df.groupby('date').apply(lambda x: pd.to_numeric(x['tpr_value'], errors='coerce').sum())
    gcf_total = df.groupby('date').apply(lambda x: pd.to_numeric(x['gcf_value'], errors='coerce').sum())
    combined = pd.DataFrame({'TPR': tpr_total, 'GCF': gcf_total}).fillna(0)
    total = combined.sum(axis=1)
    pct = combined.div(total, axis=0) * 100

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=pct.index, y=pct['TPR'], mode='lines', name='Tri-Party', line=dict(color='#3b82f6', width=2), stackgroup='one'))
    fig2.add_trace(go.Scatter(x=pct.index, y=pct['GCF'], mode='lines', name='GCF Repo', line=dict(color='#f59e0b', width=2), stackgroup='one'))
    fig2.update_layout(**_base_layout(title_text="Proporción del Mercado: Tri-Party vs GCF (%)", yaxis_title="%", yaxis_range=[0, 100]))
    return fig1, fig2


# ============================================================
# Vistas — Overnight vs Term
# ============================================================
def _view_overnight_term(period_days):
    df = _load_asset_classes(period_days)
    if df.empty:
        e = empty_figure("Sin datos de overnight/term")
        return e, e

    df['date'] = pd.to_datetime(df['date'])
    for col in ['overnight', 'term']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    colors_t = {'Treasury': '#3b82f6', 'Agency MBS': '#22c55e', 'Agency (other than MBS)': '#f59e0b'}

    fig1 = go.Figure()
    for ct in df['collateral_type'].unique():
        sub = df[df['collateral_type'] == ct].sort_values('date')
        c = colors_t.get(ct, '#888')
        fig1.add_trace(go.Bar(x=sub['date'], y=sub['overnight'], name=f'{ct} (Overnight)', marker_color=c, opacity=0.8))
        fig1.add_trace(go.Bar(x=sub['date'], y=sub['term'], name=f'{ct} (Term)', marker_color=c, opacity=0.4))
    fig1.update_layout(**_base_layout(title_text="GCF Repo: Overnight vs Term por Tipo de Colateral", yaxis_title="Miles de millones USD"), barmode='group')

    # Ratio overnight / total
    by_date = df.groupby('date')[['overnight', 'term']].sum()
    total = by_date['overnight'] + by_date['term']
    ratio = (by_date['overnight'] / total * 100).fillna(0)
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=ratio.index, y=ratio, mode='lines+markers', name='% Overnight', line=dict(color='#8b5cf6', width=2.5), marker=dict(size=5), fill='tozeroy', fillcolor='rgba(139, 92, 246, 0.12)'))
    avg = ratio.mean()
    fig2.add_hline(y=avg, line_dash="dash", line_color="rgba(255,255,255,0.4)", annotation_text=f"Media: {avg:.1f}%", annotation_position="top right", annotation_font_color="rgba(255,255,255,0.6)")
    fig2.update_layout(**_base_layout(title_text="Porcentaje Overnight sobre el Total GCF", yaxis_title="% Overnight", showlegend=False))
    return fig1, fig2


# ============================================================
# Vistas — CUSIPs
# ============================================================
def _view_cusips(period_days):
    df = _load_cusips(period_days)
    if df.empty:
        e = empty_figure("Sin datos de CUSIPs")
        return e, e

    df['date'] = pd.to_datetime(df['date'])
    for col in ['overnight', 'term']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df['total'] = df['overnight'].fillna(0) + df['term'].fillna(0)

    g = df.pivot_table(index='date', columns='collateral_type', values='total', aggfunc='sum').fillna(0)

    fig1 = go.Figure()
    for col in sorted(g.columns):
        fig1.add_trace(go.Scatter(x=g.index, y=g[col], mode='lines', name=col, line=dict(width=1.5)))
    fig1.update_layout(template='plotly_dark', title_text="GCF Repo por Tipo de CUSIP (Total = Overnight + Term)", title_x=0.5, yaxis_title="Miles de millones USD", margin={'r': 220}, legend=dict(orientation='v', yanchor='top', y=1, xanchor='left', x=1.02, font=dict(size=9)))

    # Proporción apilada
    pct = g.div(g.sum(axis=1), axis=0) * 100
    fig2 = go.Figure()
    for col in sorted(pct.columns):
        fig2.add_trace(go.Scatter(x=pct.index, y=pct[col], mode='lines', name=col, stackgroup='one', line=dict(width=0.5)))
    fig2.update_layout(template='plotly_dark', title_text="Composición por CUSIP (% del Total)", title_x=0.5, yaxis_title="%", yaxis_range=[0, 100], margin={'r': 220}, legend=dict(orientation='v', yanchor='top', y=1, xanchor='left', x=1.02, font=dict(size=9)))
    return fig1, fig2