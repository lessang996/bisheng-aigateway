from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')
    app_name: str = 'Bisheng Gateway'
    environment: str = 'development'
    host: str = '0.0.0.0'
    port: int = 8000
    database_url: str = "sqlite+aiosqlite:///./gateway.db"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: float = 30.0
    db_pool_recycle: int = 1800
    db_required: bool = False
    db_auto_create: bool = True
    # Secrets and keys must be supplied by the deployment environment.
    # HS256 uses a base64-encoded secret. RS256 uses PEM private/public keys.
    jwt_secret_key: str = ''
    jwt_algorithm: str = 'HS256'
    jwt_private_key: str = ''
    jwt_public_key: str = ''
    jwt_issuer: str = 'bisheng-gateway'
    jwt_audience: str = 'bisheng-client'
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    external_api_url: str = 'https://router.fis.aliyuncs.com/finx/api'
    external_api_key: str = ''
    external_timeout_connect: float = 120.0
    external_timeout_read: float = 60.0
    external_timeout_total: float = 120.0
    external_retries: int = 2
    external_retry_backoff: float = 0.5
    log_level: str = 'INFO'
    log_file: str = 'logs/gateway.log'
    log_max_bytes: int = 10_000_000
    log_backup_count: int = 5
    rate_limit: str = '60/minute'
    max_body_size: int = 2_000_000
    cors_origins: str = '*'
    sensitive_filter_enabled: bool = True
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_seconds: int = 30
    upstream_bearer_token: str = ''
    agent_id: int = 880717454599216379
    safety_filter_enabled: bool = True
    safety_base_url: str = ''
    safety_appkey: str = ''
    safety_secret_key: str = ''
    safety_template_id: str = ''
    safety_timeout: float = 60
    redis_url: str = 'redis://localhost:6379/0'
    # Completed report SSE cache lifetime in seconds (one day by default).
    redis_cache_ttl: int = 86400
    redis_max_connections: int = 50
    redis_connect_timeout: float = 3.0
    redis_socket_timeout: float = 3.0
    redis_health_check_interval: int = 30

    @field_validator('jwt_algorithm')
    @classmethod
    def validate_algorithm(cls, v: str) -> str:
        v = v.upper()
        if v not in {'HS256', 'RS256'}:
            raise ValueError('JWT_ALGORITHM must be HS256 or RS256')
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(',') if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
