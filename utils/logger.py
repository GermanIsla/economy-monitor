# utils/logger.py
# Sistema de logging centralizado con rotación de archivos

import logging
import os
from logging.handlers import RotatingFileHandler
from config.settings import LOG_DIR


def get_logger(name: str) -> logging.Logger:
    """
    Crea un logger con salida a archivo rotado y consola.
    Cada módulo obtiene su propio logger y su propio archivo de log.
    
    Uso:
        from utils.logger import get_logger
        logger = get_logger("mi_modulo")
        logger.info("Mensaje informativo")
        logger.error("Algo falló", exc_info=True)
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '%(asctime)s | %(name)-25s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Archivo rotado: max 5MB, mantiene 3 backups
        file_handler = RotatingFileHandler(
            os.path.join(LOG_DIR, f"{name}.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)

        # Consola
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger
