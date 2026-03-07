# db/models/base.py
# Clase base para todos los modelos SQLAlchemy del proyecto

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import DateTime, func


class Base(DeclarativeBase):
    """Clase base declarativa para todos los modelos."""
    pass


class TimestampMixin:
    """
    Mixin que añade campos de auditoría automáticos a cualquier tabla.
    
    - created_at: Se establece automáticamente al insertar el registro
    - updated_at: Se actualiza automáticamente en cada modificación
    
    Usar en todas las tablas de datos. No es necesario en tablas
    de metadatos que ya tienen sus propios campos temporales.
    """
    created_at: Mapped[DateTime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
