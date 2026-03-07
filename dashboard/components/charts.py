# dashboard/components/charts.py
# Utilidades para gráficos Plotly con estilo consistente

import plotly.graph_objects as go


# Plantilla base para todos los gráficos del proyecto
CHART_LAYOUT = dict(
    template='plotly_dark',
    font={'family': 'system-ui, -apple-system, sans-serif'},
    title_x=0.5,
    legend={'orientation': 'h', 'y': -0.15},
    margin={'l': 60, 'r': 30, 't': 60, 'b': 60},
)


def apply_standard_layout(fig: go.Figure, title: str = None) -> go.Figure:
    """Aplica el estilo estándar del proyecto a cualquier gráfico Plotly."""
    fig.update_layout(**CHART_LAYOUT)
    if title:
        fig.update_layout(title_text=title)
    return fig


def empty_figure(message: str = "Sin datos disponibles") -> go.Figure:
    """Genera un gráfico vacío con un mensaje centrado."""
    fig = go.Figure()
    fig.update_layout(
        **CHART_LAYOUT,
        annotations=[{
            'text': message,
            'xref': 'paper', 'yref': 'paper',
            'x': 0.5, 'y': 0.5,
            'showarrow': False,
            'font': {'size': 16, 'color': 'gray'}
        }],
        xaxis={'visible': False},
        yaxis={'visible': False},
    )
    return fig
