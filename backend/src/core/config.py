"""
Configuration Management for AI Tech News Assistant
==================================================

This module handles all application configuration using Pydantic settings.
It supports environment variables, multiple environments (dev/staging/prod),
secure secrets management, and configuration validation.
"""

import os
import secrets
from enum import Enum
from typing import List, Optional, Dict, Any
from functools import lru_cache

from pydantic import Field, field_validator, model_validator, SecretStr
from pydantic_settings import BaseSettings


class Environment(str, Enum):
    """Application environment types."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class LogLevel(str, Enum):
    """Logging levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class DatabaseType(str, Enum):
    """Supported database types."""
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    HUGGINGFACE = "huggingface"
    GROQ = "groq"


class Settings(BaseSettings):
    """
    Application settings with environment variable support and validation.
    
    Supports multiple environments (dev/staging/prod) with appropriate defaults
    and security configurations for each environment.
    """
    
    # Application settings
    app_name: str = Field(default="AI Tech News Assistant", alias="APP_NAME")
    version: str = Field(default="2.0.0", alias="VERSION")
    app_mode: str = Field(default="development", alias="APP_MODE")
    environment: Environment = Field(default=Environment.DEVELOPMENT, alias="ENVIRONMENT")
    debug: bool = Field(default=True, alias="DEBUG")
    use_mock_data: bool = Field(default=False, alias="USE_MOCK_DATA")
    secret_key: SecretStr = Field(default_factory=lambda: SecretStr(secrets.token_urlsafe(32)), alias="SECRET_KEY")
    
    # Server settings
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT", ge=1, le=65535)
    reload: bool = Field(default=True, alias="RELOAD")
    workers: int = Field(default=1, alias="WORKERS", ge=1, le=8)
    
    # CORS settings
    allowed_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000"],
        alias="ALLOWED_ORIGINS"
    )
    allow_credentials: bool = Field(default=True, alias="ALLOW_CREDENTIALS")
    allowed_methods: List[str] = Field(default=["*"], alias="ALLOWED_METHODS")
    allowed_headers: List[str] = Field(default=["*"], alias="ALLOWED_HEADERS")
    
    # Database settings
    database_type: DatabaseType = Field(default=DatabaseType.SQLITE, alias="DATABASE_TYPE")
    database_url: Optional[str] = Field(default=None, alias="DATABASE_URL")
    sqlite_database_path: str = Field(default="./data/articles.db", alias="SQLITE_DATABASE_PATH")
    database_pool_size: int = Field(default=5, alias="DATABASE_POOL_SIZE", ge=1, le=20)
    database_max_overflow: int = Field(default=10, alias="DATABASE_MAX_OVERFLOW", ge=0, le=50)
    database_timeout: int = Field(default=30, alias="DATABASE_TIMEOUT", ge=1, le=300)
    
    # LLM Provider Configuration
    default_llm_provider: LLMProvider = Field(default=LLMProvider.OLLAMA, alias="DEFAULT_LLM_PROVIDER")
    
    # OpenAI settings
    openai_api_key: Optional[SecretStr] = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-3.5-turbo", alias="OPENAI_MODEL")
    openai_max_tokens: int = Field(default=1000, alias="OPENAI_MAX_TOKENS", ge=1, le=4000)
    openai_temperature: float = Field(default=0.7, alias="OPENAI_TEMPERATURE", ge=0.0, le=2.0)
    openai_timeout: int = Field(default=30, alias="OPENAI_TIMEOUT", ge=1, le=300)
    
    # Anthropic settings
    anthropic_api_key: Optional[SecretStr] = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-3-haiku-20240307", alias="ANTHROPIC_MODEL")
    anthropic_max_tokens: int = Field(default=1000, alias="ANTHROPIC_MAX_TOKENS", ge=1, le=4000)
    anthropic_temperature: float = Field(default=0.7, alias="ANTHROPIC_TEMPERATURE", ge=0.0, le=1.0)
    anthropic_timeout: int = Field(default=30, alias="ANTHROPIC_TIMEOUT", ge=1, le=300)
    
    # HuggingFace settings
    huggingface_api_key: Optional[SecretStr] = Field(default=None, alias="HUGGINGFACE_API_KEY")
    huggingface_model: str = Field(default="microsoft/DialoGPT-medium", alias="HUGGINGFACE_MODEL")
    huggingface_timeout: int = Field(default=30, alias="HUGGINGFACE_TIMEOUT", ge=1, le=300)
    
    # Ollama settings
    ollama_host: str = Field(default="http://localhost:11434", alias="OLLAMA_HOST")
    ollama_model: str = Field(default="llama3.2", alias="OLLAMA_MODEL")
    ollama_timeout: int = Field(default=60, alias="OLLAMA_TIMEOUT", ge=1, le=300)
    ollama_keep_alive: str = Field(default="5m", alias="OLLAMA_KEEP_ALIVE")

    # Groq settings (OpenAI-compatible API; used when DEFAULT_LLM_PROVIDER=groq).
    groq_api_key: Optional[SecretStr] = Field(default=None, alias="GROQ_API_KEY")
    groq_base_url: str = Field(
        default="https://api.groq.com/openai/v1", alias="GROQ_BASE_URL"
    )
    groq_model: str = Field(
        default="llama-3.3-70b-versatile", alias="GROQ_MODEL"
    )
    groq_timeout: int = Field(default=120, alias="GROQ_TIMEOUT", ge=1, le=600)
    
    # Embedding settings
    embedding_model: str = Field(default="all-MiniLM-L6-v2", alias="EMBEDDING_MODEL")
    embedding_batch_size: int = Field(default=32, alias="EMBEDDING_BATCH_SIZE", ge=1, le=128)
    embedding_dimensions: int = Field(default=384, alias="EMBEDDING_DIMENSIONS", ge=1, le=4096)
    embedding_timeout: int = Field(default=30, alias="EMBEDDING_TIMEOUT", ge=1, le=300)
    
    # Vector database settings
    chroma_persist_directory: str = Field(
        default="./data/chroma_db", 
        alias="CHROMA_PERSIST_DIRECTORY"
    )
    vector_similarity_threshold: float = Field(default=0.7, alias="VECTOR_SIMILARITY_THRESHOLD", ge=0.0, le=1.0)
    vector_max_results: int = Field(default=10, alias="VECTOR_MAX_RESULTS", ge=1, le=100)
    
    # Repository Configuration
    use_sqlalchemy_orm: bool = Field(
        default=True,
        description="Whether to use SQLAlchemy ORM or raw SQLite implementation",
        alias="USE_SQLALCHEMY_ORM"
    )
    use_vector_database: bool = Field(
        default=False,
        description="Whether to use vector database for embeddings",
        alias="USE_VECTOR_DATABASE"
    )
    use_mock_clients: bool = Field(
        default=False,
        description="Whether to use mock clients for development/testing",
        alias="USE_MOCK_CLIENTS"
    )
    
    # Scraping settings
    scraping_rate_limit: float = Field(default=2.0, alias="SCRAPING_RATE_LIMIT", ge=0.1, le=10.0)
    scraping_max_retries: int = Field(default=3, alias="SCRAPING_MAX_RETRIES", ge=0, le=10)
    scraping_timeout: int = Field(default=30, alias="SCRAPING_TIMEOUT", ge=5, le=300)
    
    # Cache settings
    cache_expiry_hours: int = Field(default=6, alias="CACHE_EXPIRY_HOURS", ge=1, le=168)

    # Retention settings (Milestone 3 — daily retention cron)
    retention_enabled: bool = Field(default=True, alias="RETENTION_ENABLED")
    retention_days: int = Field(default=30, alias="RETENTION_DAYS", ge=1, le=3650)
    retention_max_deletes: int = Field(default=500, alias="RETENTION_MAX_DELETES", ge=1, le=100000)

    # Per-article subagents settings (Mission 2, Milestone 3 — SubagentPool)
    # Caps the number of in-flight per-article skill dispatches running
    # concurrently inside the agent's fan-out step. Default 4 keeps Ollama
    # latency reasonable on a single-GPU box; bump for more cores.
    max_concurrent_subagents: int = Field(
        default=4,
        alias="MAX_CONCURRENT_SUBAGENTS",
        ge=1,
        le=64,
    )

    # Per-article subagents settings (Mission 2, Milestone 6 — Ingestion migration)
    # When True, ``SummarizationOrchestrator`` calls the
    # ``agent_skills.summarize_article`` skill (which uses the cache +
    # write-back path shared with research-time). When False, the legacy
    # ``SummarizationService.summarize_content`` direct-call path runs —
    # kept as an emergency rollback hatch. Flip to False if a regression
    # surfaces in the wild; the flag itself is slated for removal in the
    # post-M6 cleanup PR.
    use_agent_skill_summarization: bool = Field(
        default=True,
        alias="USE_AGENT_SKILL_SUMMARIZATION",
    )

    # News sources settings
    rss_sources: List[Dict[str, str]] = Field(
        default=[
            {
                # Feedburner deprecated and now serves 404; canonical
                # feed lives on oreilly.com directly. (probe_feeds.py
                # caught this during the 4/5-feeds-accessible triage.)
                "name": "O'Reilly Radar",
                "url": "https://www.oreilly.com/radar/feed/",
                "description": "O'Reilly Radar tech insights"
            },
            {
                "name": "TechCrunch",
                "url": "https://techcrunch.com/feed/",
                "description": "TechCrunch startup and tech news"
            },
            {
                "name": "Ars Technica", 
                "url": "https://feeds.arstechnica.com/arstechnica/index",
                "description": "Ars Technica technology news and analysis"
            },
            {
                "name": "The Verge",
                "url": "https://www.theverge.com/rss/index.xml", 
                "description": "The Verge technology, science, art, and culture"
            },
            {
                "name": "MIT Technology Review",
                "url": "https://www.technologyreview.com/feed/",
                "description": "MIT Technology Review"
            }
        ],
        alias="RSS_SOURCES"
    )
    rss_timeout: int = Field(default=10, alias="RSS_TIMEOUT", ge=1, le=60)
    rss_max_articles: int = Field(default=100, alias="RSS_MAX_ARTICLES", ge=1, le=1000)
    rss_update_interval: int = Field(default=3600, alias="RSS_UPDATE_INTERVAL", ge=300, le=86400)  # 5 min to 24 hours
    
    # Logging settings
    log_level: LogLevel = Field(default=LogLevel.INFO, alias="LOG_LEVEL")
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        alias="LOG_FORMAT"
    )
    log_file: Optional[str] = Field(default=None, alias="LOG_FILE")
    log_max_size: int = Field(default=10 * 1024 * 1024, alias="LOG_MAX_SIZE")  # 10MB
    log_backup_count: int = Field(default=5, alias="LOG_BACKUP_COUNT")
    
    # Error handling settings
    enable_error_middleware: bool = Field(default=True, alias="ENABLE_ERROR_MIDDLEWARE")
    enable_correlation_id: bool = Field(default=True, alias="ENABLE_CORRELATION_ID")
    error_detail_in_response: bool = Field(default=False, alias="ERROR_DETAIL_IN_RESPONSE")  # Only for dev
    
    # Retry and resilience settings
    default_retry_attempts: int = Field(default=3, alias="DEFAULT_RETRY_ATTEMPTS")
    default_retry_delay: float = Field(default=1.0, alias="DEFAULT_RETRY_DELAY")
    circuit_breaker_threshold: int = Field(default=5, alias="CIRCUIT_BREAKER_THRESHOLD")
    circuit_breaker_timeout: int = Field(default=60, alias="CIRCUIT_BREAKER_TIMEOUT")
    
    # Monitoring settings
    enable_metrics: bool = Field(default=True, alias="ENABLE_METRICS")
    metrics_endpoint: str = Field(default="/metrics", alias="METRICS_ENDPOINT")
    health_check_timeout: float = Field(default=5.0, alias="HEALTH_CHECK_TIMEOUT")
    
    # Rate limiting settings
    rate_limit_requests: int = Field(default=100, alias="RATE_LIMIT_REQUESTS")
    rate_limit_window: int = Field(default=60, alias="RATE_LIMIT_WINDOW")  # seconds
    
    # External service timeouts
    llm_request_timeout: float = Field(default=30.0, alias="LLM_REQUEST_TIMEOUT")
    embedding_request_timeout: float = Field(default=15.0, alias="EMBEDDING_REQUEST_TIMEOUT")
    news_fetch_timeout: float = Field(default=10.0, alias="NEWS_FETCH_TIMEOUT")
    
    # Security settings
    enable_cors: bool = Field(default=True, alias="ENABLE_CORS")
    max_content_length: int = Field(default=16 * 1024 * 1024, alias="MAX_CONTENT_LENGTH")  # 16MB
    trusted_hosts: List[str] = Field(default=["*"], alias="TRUSTED_HOSTS")
    
    # Cache settings
    enable_caching: bool = Field(default=True, alias="ENABLE_CACHING")
    cache_ttl: int = Field(default=3600, alias="CACHE_TTL", ge=60, le=86400)  # 1 min to 24 hours
    cache_max_size: int = Field(default=1000, alias="CACHE_MAX_SIZE", ge=10, le=10000)
    
    # Development settings
    auto_reload: bool = Field(default=True, alias="AUTO_RELOAD")
    enable_profiling: bool = Field(default=False, alias="ENABLE_PROFILING")
    enable_debug_toolbar: bool = Field(default=False, alias="ENABLE_DEBUG_TOOLBAR")
    
    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v):
        """Validate environment value."""
        if isinstance(v, str):
            try:
                return Environment(v.lower())
            except ValueError:
                raise ValueError(f"Invalid environment: {v}. Must be one of: {list(Environment)}")
        return v
    
    @field_validator("secret_key")
    @classmethod
    def validate_secret_key_length(cls, v):
        """Ensure secret key is strong enough."""
        if isinstance(v, SecretStr):
            secret_value = v.get_secret_value()
        else:
            secret_value = str(v)
        
        if len(secret_value) < 32:
            raise ValueError("Secret key must be at least 32 characters long")
        return v
    
    @field_validator("ollama_host")
    @classmethod
    def validate_ollama_host(cls, v):
        """Validate Ollama host URL."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("Ollama host must be a valid HTTP/HTTPS URL")
        return v
    
    @model_validator(mode='after')
    def validate_production_settings(self):
        """Validate production-specific settings."""
        if self.environment == Environment.PRODUCTION:
            if self.debug:
                raise ValueError("Debug mode cannot be enabled in production environment")
            
            if "*" in self.allowed_origins:
                raise ValueError("Wildcard CORS origins not allowed in production")
            
            if self.database_type != DatabaseType.SQLITE and not self.database_url:
                raise ValueError("Database URL is required for production with non-SQLite databases")
        
        return self
    
    def get_database_path(self) -> str:
        """Get the appropriate database path based on configuration.

        This is THE single source of truth for "where is the database".
        Precedence: ``DATABASE_URL`` if set, else ``SQLITE_DATABASE_PATH``
        (default ``./data/articles.db``). Every module that needs a
        database location — raw sqlite3 path or SQLAlchemy URL — should
        derive it from this method (via :meth:`get_database_file_path` or
        :meth:`get_database_sqlalchemy_url` below) rather than reading
        ``database_url`` / ``sqlite_database_path`` directly. Historically
        several call sites read ``sqlite_database_path`` on its own
        (ignoring ``DATABASE_URL``) or hardcoded their own fallback path,
        which let the write path and read path silently resolve to two
        different SQLite files under stock defaults.
        """
        if self.database_url:
            return self.database_url
        return self.sqlite_database_path

    def get_database_file_path(self) -> str:
        """Resolve the configured database location to a plain filesystem
        path, suitable for ``sqlite3.connect()``.

        ``get_database_path()`` may return either a bare path
        (``./data/articles.db``) or a SQLAlchemy-style URL
        (``sqlite:////data/articles.db``, e.g. when ``DATABASE_URL`` is
        set on Fly). This strips the ``sqlite://`` / ``sqlite:///``
        scheme either way so callers always get something ``sqlite3``
        understands.
        """
        raw = self.get_database_path()
        if raw.startswith("sqlite:///"):
            path = raw[len("sqlite:///"):]
        elif raw.startswith("sqlite://"):
            path = raw[len("sqlite://"):]
        else:
            path = raw
        self._ensure_parent_dir(path)
        return path

    @staticmethod
    def _ensure_parent_dir(path: str) -> None:
        """Create the parent directory for a sqlite file path if needed.

        Every consumer of the resolved database path (raw sqlite3 or
        SQLAlchemy) connects through here or through
        :meth:`get_database_sqlalchemy_url`, so this is the one place that
        needs to guarantee the directory exists. Without it, whichever
        module happens to open the connection first on a fresh checkout
        (e.g. ``ArticleRepository`` during app startup) fails with
        "unable to open database file", and a later module racing in
        (SQLAlchemy's ``create_all``, which does create its own parent
        dir) ends up creating the ``articles`` table first with a
        different, reduced schema.
        """
        if not path or path == ":memory:":
            return
        dir_path = os.path.dirname(path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

    def get_database_sqlalchemy_url(self) -> str:
        """Resolve the configured database location to a SQLAlchemy
        connection URL (e.g. ``sqlite:///./data/articles.db``).

        ``get_database_path()`` may return a bare filesystem path when
        only ``SQLITE_DATABASE_PATH`` is set; this adds the ``sqlite:///``
        scheme in that case so the SQLAlchemy engine and the raw-sqlite3
        code paths always agree on the same underlying file.
        """
        raw = self.get_database_path()
        url = raw if "://" in raw else f"sqlite:///{raw}"
        if url.startswith("sqlite:///"):
            self._ensure_parent_dir(url[len("sqlite:///"):])
        elif url.startswith("sqlite://"):
            self._ensure_parent_dir(url[len("sqlite://"):])
        return url

    def get_llm_config(self, provider: Optional[LLMProvider] = None) -> Dict[str, Any]:
        """Get LLM configuration for specified provider."""
        provider = provider or self.default_llm_provider
        
        configs = {
            LLMProvider.OPENAI: {
                "api_key": self.openai_api_key.get_secret_value() if self.openai_api_key else None,
                "model": self.openai_model,
                "max_tokens": self.openai_max_tokens,
                "temperature": self.openai_temperature,
                "timeout": self.openai_timeout,
            },
            LLMProvider.ANTHROPIC: {
                "api_key": self.anthropic_api_key.get_secret_value() if self.anthropic_api_key else None,
                "model": self.anthropic_model,
                "max_tokens": self.anthropic_max_tokens,
                "temperature": self.anthropic_temperature,
                "timeout": self.anthropic_timeout,
            },
            LLMProvider.HUGGINGFACE: {
                "api_key": self.huggingface_api_key.get_secret_value() if self.huggingface_api_key else None,
                "model": self.huggingface_model,
                "timeout": self.huggingface_timeout,
            },
            LLMProvider.OLLAMA: {
                "host": self.ollama_host,
                "model": self.ollama_model,
                "timeout": self.ollama_timeout,
                "keep_alive": self.ollama_keep_alive,
            },
        }
        
        return configs.get(provider, {})
    
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == Environment.PRODUCTION
    
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == Environment.DEVELOPMENT
    
    def is_testing(self) -> bool:
        """Check if running in testing environment."""
        return self.environment == Environment.TESTING
    
    @property
    def database_path(self) -> str:
        """Get database path (alias for sqlite_database_path for compatibility)."""
        return self.sqlite_database_path
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8", 
        "case_sensitive": False,
        "use_enum_values": True,
        "validate_assignment": True,
        "populate_by_name": True,  # Allows using both field names and aliases
        "extra": "ignore"  # Ignore unknown environment variables (e.g., deprecated LLM_PROVIDER)
    }



@lru_cache()
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()


# Global settings instance
settings = get_settings()
