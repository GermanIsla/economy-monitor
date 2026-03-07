# utils/rate_limiter.py
# Control de velocidad para peticiones a APIs externas

import time
from functools import wraps
from config.settings import DEFAULT_RATE_LIMIT


class RateLimiter:
    """
    Controla la velocidad de peticiones a una API.
    Cada fuente de datos usa su propia instancia con su intervalo.
    
    Uso:
        limiter = RateLimiter(min_interval=0.5)  # 0.5 segundos entre peticiones
        
        for page in range(1, total_pages + 1):
            limiter.wait()  # Espera automáticamente si es necesario
            response = requests.get(url, params={'page': page})
    """

    def __init__(self, min_interval: float = DEFAULT_RATE_LIMIT):
        """
        Args:
            min_interval: Segundos mínimos entre peticiones consecutivas.
        """
        self.min_interval = min_interval
        self.last_call = 0.0

    def wait(self):
        """Espera el tiempo necesario antes de la siguiente petición."""
        elapsed = time.time() - self.last_call
        if elapsed < self.min_interval:
            sleep_time = self.min_interval - elapsed
            time.sleep(sleep_time)
        self.last_call = time.time()

    def throttle(self, func):
        """Decorador para aplicar rate limiting a cualquier función."""
        @wraps(func)
        def wrapper(*args, **kwargs):
            self.wait()
            return func(*args, **kwargs)
        return wrapper
