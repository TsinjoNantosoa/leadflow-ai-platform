"""Configuration unique de l'application (12-factor) : tout vient de l'environnement."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # env_ignore_empty : `VAR=` vide (cas de .env.example copié tel quel) = variable absente => valeur par défaut.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True)

    # --- Application -------------------------------------------------------------------------
    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "LeadFlow AI"
    log_level: str = "INFO"
    default_org_slug: str = "novadigital"

    # --- Base de données ---------------------------------------------------------------------
    # Neon : utiliser l'URL "pooled" ici et, si possible, l'URL directe dans DATABASE_URL_DIRECT
    # (utilisée uniquement par Alembic).
    database_url: str = "postgresql+psycopg://leadflow:leadflow_local@localhost:5433/leadflow"
    database_url_direct: str = ""
    db_pool_size: int = Field(5, ge=1, le=50)
    db_max_overflow: int = Field(5, ge=0, le=50)
    db_pool_recycle_seconds: int = Field(300, ge=30)
    db_pool_timeout_seconds: int = Field(30, ge=1)
    db_connect_timeout_seconds: int = Field(15, ge=1)

    # --- Web / sessions ----------------------------------------------------------------------
    frontend_url: str = "http://localhost:5173"
    cors_allowed_origins: str = ""  # origines supplémentaires, séparées par des virgules
    session_secret: SecretStr = SecretStr("dev-only-session-secret-change-me-0123456789")
    session_ttl_hours: int = Field(12, ge=1, le=168)
    session_cookie_name: str = "lf_session"
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_cookie_secure: bool | None = None  # None => True en production
    login_max_failures: int = Field(5, ge=1)
    login_lock_minutes: int = Field(15, ge=1)
    trust_proxy_headers: bool = False

    # --- Public API --------------------------------------------------------------------------
    public_rate_limit_per_hour: int = Field(25, ge=1)
    max_lead_message_length: int = Field(4000, ge=100, le=20000)
    privacy_notice_version: str = "2026-10-v1"

    # --- Endpoints internes (n8n -> FastAPI) -------------------------------------------------
    api_service_token: SecretStr = SecretStr("")
    internal_max_clock_skew_seconds: int = Field(300, ge=30)

    # --- LLM ---------------------------------------------------------------------------------
    llm_provider: Literal["mock", "openai"] = "mock"
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = ""
    llm_timeout_seconds: float = Field(30.0, gt=0)
    llm_max_retries: int = Field(2, ge=0, le=5)
    llm_backoff_base_seconds: float = Field(1.0, ge=0)
    llm_max_output_tokens_extraction: int = Field(600, ge=100, le=4000)
    llm_max_output_tokens_draft: int = Field(900, ge=100, le=4000)
    llm_max_concurrency: int = Field(4, ge=1, le=32)
    llm_daily_call_limit: int = Field(0, ge=0, description="0 = illimité")
    # Tarifs en USD par million de tokens. Laisser vide : aucune estimation de coût n'est produite.
    llm_price_input_per_mtok: float | None = Field(None, ge=0)
    llm_price_output_per_mtok: float | None = Field(None, ge=0)

    # --- CRM / e-mail ------------------------------------------------------------------------
    # Les credentials HubSpot vivent uniquement dans n8n ; le backend ne connaît que le mode.
    crm_provider: Literal["mock", "hubspot"] = "mock"
    enable_real_email_send: bool = False

    # --- Outbox ------------------------------------------------------------------------------
    outbox_lease_seconds: int = Field(300, ge=30)
    outbox_max_attempts: int = Field(5, ge=1, le=20)
    outbox_backoff_base_seconds: int = Field(30, ge=1)
    outbox_backoff_max_seconds: int = Field(3600, ge=30)
    outbox_claim_batch_max: int = Field(20, ge=1, le=100)

    # --- Rétention ---------------------------------------------------------------------------
    retention_outbox_days: int = Field(30, ge=1)
    retention_idempotency_days: int = Field(7, ge=1)
    retention_sessions_days: int = Field(7, ge=1)

    # --- Seed de démonstration (jamais de mot de passe par défaut) -----------------------------
    demo_admin_password: SecretStr = SecretStr("")
    demo_sales_password: SecretStr = SecretStr("")

    # ------------------------------------------------------------------------------------------
    @field_validator("database_url", "database_url_direct")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://") :]
        if v.startswith("postgresql://"):
            v = "postgresql+psycopg://" + v[len("postgresql://") :]
        return v

    @field_validator("enable_real_email_send")
    @classmethod
    def _no_email_in_mvp(cls, v: bool) -> bool:
        if v:
            raise ValueError("ENABLE_REAL_EMAIL_SEND doit rester false : aucun envoi d'e-mail dans le MVP")
        return v

    @model_validator(mode="after")
    def _check_consistency(self) -> Settings:
        if self.llm_provider == "openai":
            if not self.openai_api_key.get_secret_value():
                raise ValueError("OPENAI_API_KEY est requis quand LLM_PROVIDER=openai")
            if not self.openai_model.strip():
                raise ValueError("OPENAI_MODEL est requis quand LLM_PROVIDER=openai")
        if self.session_cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("SESSION_COOKIE_SAMESITE=none exige un cookie Secure (HTTPS)")
        if self.app_env == "production":
            if len(self.session_secret.get_secret_value()) < 32 or "dev-only" in self.session_secret.get_secret_value():
                raise ValueError("SESSION_SECRET (>= 32 caractères, aléatoire) est requis en production")
            if len(self.api_service_token.get_secret_value()) < 32:
                raise ValueError("API_SERVICE_TOKEN (>= 32 caractères) est requis en production")
        return self

    # ------------------------------------------------------------------------------------------
    @property
    def cookie_secure(self) -> bool:
        if self.session_cookie_secure is not None:
            return self.session_cookie_secure
        return self.app_env == "production"

    @property
    def allowed_origins(self) -> list[str]:
        origins = [self.frontend_url.rstrip("/")]
        origins += [o.strip().rstrip("/") for o in self.cors_allowed_origins.split(",") if o.strip()]
        seen: list[str] = []
        for o in origins:
            if o and o not in seen:
                seen.append(o)
        return seen

    @property
    def alembic_url(self) -> str:
        return self.database_url_direct or self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
