# db/engine.py
# Motor de base de datos SQLAlchemy con SQLite y WAL mode

from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from config.settings import DB_URL, DB_ECHO

# Crear el engine de SQLAlchemy
engine = create_engine(DB_URL, echo=DB_ECHO)


# Activar WAL mode para mejor concurrencia lectura/escritura en SQLite
# WAL permite que el scheduler escriba mientras el dashboard lee sin bloqueos
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")  # Esperar hasta 5s si la DB está bloqueada
    cursor.close()


# Factoría de sesiones
SessionLocal = sessionmaker(bind=engine)


@contextmanager
def get_session() -> Session:
    """
    Context manager para sesiones de base de datos.
    Hace rollback automático si hay excepción, y close siempre.
    
    Uso:
        with get_session() as session:
            results = session.execute(stmt).scalars().all()
            session.commit()  # Solo si has escrito datos
    """
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    """
    Crea todas las tablas definidas en los modelos.
    Seguro de ejecutar múltiples veces (solo crea lo que falta).
    
    En producción, usar Alembic para migraciones.
    Para desarrollo inicial, esta función es suficiente.
    """
    from db.models.base import Base
    # Importar todos los modelos para que Base los registre
    import db.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
