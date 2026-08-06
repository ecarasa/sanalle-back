from pydantic import BaseModel, field_validator


class TipoIvaBase(BaseModel):
    nombre: str
    tasa: float
    discrimina: str

    @field_validator("nombre")
    @classmethod
    def format_nombre(cls, v: str) -> str:
        return v.strip().title() if v else v


class TipoIvaCreate(TipoIvaBase):
    pass


class TipoIvaUpdate(BaseModel):
    nombre: str | None = None
    tasa: float | None = None
    discrimina: str | None = None


class TipoIvaResponse(TipoIvaBase):
    id: int
    model_config = {"from_attributes": True}
