import os
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv
from pydantic import SecretStr
from pydantic.functional_validators import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.schemas.types import EnvironmentEnum


class BaseConfig(BaseSettings):
    """Application settings class containing database and other credentials."""

    # ===== API SERVER =====
    ENV: EnvironmentEnum = EnvironmentEnum.DEVELOPMENT
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 1

    # ===== REDIS CACHE =====
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: SecretStr = SecretStr("your_redis_password")
    REDIS_DB: int = 0

    @field_validator(
        "PORT", "POSTGRES_PORT", "REDIS_PORT", "AWS_S3_PORT", mode="before"
    )
    @classmethod
    def parse_port_fields(cls, v: str | int) -> int:
        """Parses port fields to ensure they are integers."""
        if isinstance(v, str):
            try:
                return int(v.strip())
            except ValueError:
                raise ValueError(f"Invalid port value: {v}") from None

        if isinstance(v, int) and not (1 <= v <= 65535):
            raise ValueError(f"Port must be between 1 and 65535, got {v}")

        return v

    @property
    def redis_url(self) -> str:
        """
        Constructs the Redis connection URL.

        Returns
        -------
        str
            Complete Redis connection URL in the format:
            redis://[:password@]host:port/db
        """
        raw_password = self.REDIS_PASSWORD.get_secret_value()
        if raw_password:
            password = quote(raw_password, safe="")
            url: str = f"redis://:{password}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        else:
            url = f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return url


def setup_env() -> None:
    """Sets environment variables."""
    pass


class DevelopmentConfig(BaseConfig):
    """Development environment settings."""

    model_config = SettingsConfigDict(
        env_file=str(Path(".env").absolute()),
        env_file_encoding="utf-8",
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    ENV: EnvironmentEnum = EnvironmentEnum.DEVELOPMENT
    WORKERS: int = 1
    LIMIT_VALUE: int = 20
    RELOAD: bool = True
    DEBUG: bool = True


class SandboxConfig(BaseConfig):
    """Sandbox environment settings."""

    model_config = SettingsConfigDict(
        env_file=str(Path(".env.sandbox").absolute()),
        env_file_encoding="utf-8",
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    ENV: EnvironmentEnum = EnvironmentEnum.SANDBOX
    WORKERS: int = 1
    LIMIT_VALUE: int = 30
    RELOAD: bool = False
    DEBUG: bool = False


class ProductionConfig(BaseConfig):
    """Production environment settings."""

    model_config = SettingsConfigDict(
        env_file=str(Path(".env.prod").absolute()),
        env_file_encoding="utf-8",
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    ENV: EnvironmentEnum = EnvironmentEnum.PRODUCTION
    WORKERS: int = 2
    LIMIT_VALUE: int = 60
    RELOAD: bool = False
    DEBUG: bool = False


type ConfigType = DevelopmentConfig | ProductionConfig | SandboxConfig


def refresh_settings() -> ConfigType:
    """Refresh environment variables and return new Settings instance.

    This function reloads environment variables from .env file and creates
    a new Settings instance with the updated values.

    Returns
    -------
    ConfigType
        An instance of the appropriate Settings subclass based on the ENV variable.
    """
    load_dotenv(override=True)
    # Determine environment type; `development` is the default
    env_str = os.getenv("ENV", EnvironmentEnum.DEVELOPMENT.value)
    env = EnvironmentEnum(env_str)
    print(f"Loading configuration for environment: {env.value}")

    configs = {
        EnvironmentEnum.DEVELOPMENT: DevelopmentConfig,
        EnvironmentEnum.PRODUCTION: ProductionConfig,
        EnvironmentEnum.SANDBOX: SandboxConfig,
        # Map both SANDBOX and STAGING to SandboxConfig
        EnvironmentEnum.STAGING: SandboxConfig,
    }
    config_cls: type[ConfigType] = configs.get(env, DevelopmentConfig)

    return config_cls()  # type: ignore


app_settings: ConfigType = refresh_settings()

# Call setup_env only once at startup
_setup_env_called: bool = False


def setup_env_once() -> None:
    """Sets environment variables for Together AI and OpenRouter clients. Called only once."""
    global _setup_env_called
    if not _setup_env_called:
        setup_env()
        _setup_env_called = True


# Automatically call setup_env when the module is imported
setup_env_once()
