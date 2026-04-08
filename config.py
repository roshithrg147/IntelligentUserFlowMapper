from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr

class Settings(BaseSettings):
    crawler_username: SecretStr | None = Field(default=None, alias="CRAWLER_USERNAME")
    crawler_password: SecretStr | None = Field(default=None, alias="CRAWLER_PASSWORD")
    redis_url: str = Field(default="redis://localhost", alias="REDIS_URL")
    sqlite_db_path: str = Field(default="IntelligentUserFlowMapper_Dev/results/nodes.db", alias="SQLITE_DB_PATH")
    allowed_origins: str = Field(default="*", alias="ALLOWED_ORIGINS")
    api_key: SecretStr | None = Field(default=None, alias="API_KEY")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
