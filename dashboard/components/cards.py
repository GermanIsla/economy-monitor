# dashboard/components/cards.py
# Componentes reutilizables: tarjetas de indicadores (KPI)

from dash import html
import dash_bootstrap_components as dbc


def kpi_card(
    title: str,
    value: str,
    delta: str = None,
    delta_color: str = "success",
    icon: str = "bi-graph-up"
):
    """
    Tarjeta de indicador clave (KPI) para el dashboard.
    
    Args:
        title: Nombre del indicador (ej: "Bills emitidos")
        value: Valor formateado como string (ej: "$1.23B")
        delta: Cambio respecto al periodo anterior (ej: "+2.3%")
        delta_color: "success" (verde), "danger" (rojo), "warning" (amarillo)
        icon: Clase de Bootstrap Icons (ej: "bi-cash-stack")
    """
    delta_element = html.Span(
        delta,
        className=f"badge bg-{delta_color} ms-2"
    ) if delta else None

    return dbc.Card([
        dbc.CardBody([
            html.Div([
                html.I(className=f"bi {icon} fs-4 text-primary"),
                html.Span(title, className="ms-2 text-muted small"),
            ]),
            html.Div([
                html.H3(value, className="mb-0 mt-2"),
                delta_element
            ]),
        ], className="p-3")
    ], className="h-100")
