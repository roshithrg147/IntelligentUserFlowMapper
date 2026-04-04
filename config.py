from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    crawler_username: str | None = Field(default=None, alias="CRAWLER_USERNAME")
    crawler_password: str | None = Field(default=None, alias="CRAWLER_PASSWORD")
    redis_url: str = Field(default="redis://localhost", alias="REDIS_URL")
    sqlite_db_path: str = Field(default="results/nodes.db", alias="SQLITE_DB_PATH")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
