from datetime import datetime
from pydantic import BaseModel, ConfigDict
from typing import Optional

class LaboratorioBase(BaseModel):
    nombre: str
    activo: bool = True
    # Posición en la lista de precios. 0 = sin definir (va al final, alfabético).
    orden: int = 0

class LaboratorioCreate(LaboratorioBase):
    # None = agregar al final. Distinto de 0, que significa "sin orden definido".
    orden: Optional[int] = None

class LaboratorioUpdate(BaseModel):
    nombre: Optional[str] = None
    activo: Optional[bool] = None
    orden: Optional[int] = None

class LaboratorioResponse(LaboratorioBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LaboratorioOrdenRequest(BaseModel):
    """Reordena la lista de una sola vez.

    Dos formas de decir lo mismo: `ids` para los botones ↑/↓ de la pantalla, y
    `nombres` para pegar el orden desde el PDF que manda el cliente. Lo que no
    figure en la lista queda detrás, alfabético.
    """

    ids: Optional[list[int]] = None
    nombres: Optional[list[str]] = None


class LaboratorioOrdenResponse(BaseModel):
    aplicados: int
    no_encontrados: list[str] = []
