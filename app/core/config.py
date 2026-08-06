from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    POSTGRES_USER: str = "sanalle_user"
    POSTGRES_PASSWORD: str = "sanalle_pass_2024"
    POSTGRES_DB: str = "sanalle_db"
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str = "postgresql+asyncpg://sanalle_user:sanalle_pass_2024@db:5432/sanalle_db"
    SECRET_KEY: str = "sanalle-super-secret-jwt-key-2024-drogueria"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    BACKEND_PORT: int = 8001
    PDF_STORAGE_PATH: str = "/app/storage/recibos"
    ADMIN_EMAIL: str = "admin@sanalle.com"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
    ADMIN_NOMBRE: str = "Administrador SANALLE"
    TOMTOM_API_KEY: str = "[ENCRYPTION_KEY]"
    AWS_ACCESS_KEY_ID: str = "TEST_ACCESS_KEY"
    AWS_SECRET_ACCESS_KEY: str = "TEST_SECRET_KEY"
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = "bucket_versionai"
    S3_KEY_PREFIX: str = "uploads/sanalle"
    S3_URL: str = ""
    S3_ENDPOINT_URL: str = ""
    APP_NAME: str = "SANALLE"
    # Nombre del proyecto (compartido con el frontend). Si esta seteado,
    # se usa como nombre de la empresa en PDFs y exports.
    NEXT_PUBLIC_APP_NAME: str = ""

    PVP_SCRAPER_CSS_SELECTOR: str = "td.tdprecio"
    PVP_SCRAPER_TIMEOUT: int = 15

    class Config:
        env_file = ".env"

    @model_validator(mode="after")
    def _resolve_app_name(self):
        if self.NEXT_PUBLIC_APP_NAME:
            self.APP_NAME = self.NEXT_PUBLIC_APP_NAME
        return self

    @model_validator(mode="after")
    def _normalize_database_url(self):
        # Railway (y varios PaaS) entregan la URL como `postgres://` o
        # `postgresql://`, pero la app usa el driver async (asyncpg).
        # Normalizamos para poder pegar la DATABASE_URL de Railway tal cual.
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url[len("postgresql://"):]
        self.DATABASE_URL = url
        return self


settings = Settings()
