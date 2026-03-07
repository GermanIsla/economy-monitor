# utils/helpers.py
# Funciones auxiliares compartidas por todo el proyecto

from datetime import datetime, timedelta


def format_amount(amount: float, decimals: int = 2) -> str:
    """
    Formatea una cantidad numérica de forma legible.
    Ejemplo: 1234567890 → "$1.23B"
    """
    if abs(amount) >= 1e12:
        return f"${amount / 1e12:.{decimals}f}T"
    elif abs(amount) >= 1e9:
        return f"${amount / 1e9:.{decimals}f}B"
    elif abs(amount) >= 1e6:
        return f"${amount / 1e6:.{decimals}f}M"
    elif abs(amount) >= 1e3:
        return f"${amount / 1e3:.{decimals}f}K"
    else:
        return f"${amount:.{decimals}f}"


def time_ago(dt: datetime) -> str:
    """
    Convierte un datetime a texto relativo.
    Ejemplo: datetime(hace 2 horas) → "hace 2h"
    """
    if dt is None:
        return "nunca"
    
    delta = datetime.now() - dt
    
    if delta.days > 30:
        return f"hace {delta.days // 30} meses"
    elif delta.days > 0:
        return f"hace {delta.days}d"
    elif delta.seconds > 3600:
        return f"hace {delta.seconds // 3600}h"
    elif delta.seconds > 60:
        return f"hace {delta.seconds // 60}min"
    else:
        return "ahora mismo"


def safe_float(value, default: float = 0.0) -> float:
    """Convierte un valor a float de forma segura, retornando default si falla."""
    try:
        result = float(value)
        return result if result == result else default  # Maneja NaN
    except (ValueError, TypeError):
        return default
