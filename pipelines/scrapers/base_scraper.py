# pipelines/scrapers/base_scraper.py
# Clase base para web scrapers (fuentes de datos sin API)

from abc import ABC, abstractmethod
import requests
from bs4 import BeautifulSoup
from utils.rate_limiter import RateLimiter
from utils.logger import get_logger


class BaseScraper(ABC):
    """
    Clase base para web scrapers.
    Proporciona rate limiting, User-Agent configurable, y parseo con BeautifulSoup.
    
    Para crear un scraper nuevo:
    1. Heredar de BaseScraper
    2. Implementar scrape()
    3. Usar self.fetch_page(url) para descargar y parsear páginas
    """

    def __init__(self, rate_limit: float = 2.0):
        """
        Args:
            rate_limit: Segundos entre peticiones. Más conservador que APIs
                        porque el scraping tiene más riesgo de ser bloqueado.
        """
        self.logger = get_logger(self.__class__.__name__)
        self.limiter = RateLimiter(min_interval=rate_limit)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'EconomyMonitor/1.0 (proyecto educativo personal)',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
        })

    def fetch_page(self, url: str) -> BeautifulSoup:
        """
        Descarga y parsea una página web respetando rate limits.
        
        Args:
            url: URL completa de la página a descargar
            
        Returns:
            Objeto BeautifulSoup con el contenido parseado
        """
        self.limiter.wait()
        self.logger.info(f"Descargando: {url}")
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        return BeautifulSoup(response.text, 'lxml')

    @abstractmethod
    def scrape(self) -> list[dict]:
        """
        Extrae los datos de la web.
        Retorna lista de diccionarios con los datos crudos.
        """
        pass
