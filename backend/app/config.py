import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    supabase_url: str
    supabase_service_key: str
    supabase_jwt_secret: str | None = None
    groq_api_key: str | None = None
    sarvam_api_key: str | None = None
    gemini_api_key: str | None = None
    jina_api_key: str | None = None
    telecmi_user_id: str | None = None
    telecmi_secret: str | None = None
    telecmi_agent_password: str | None = None
    telecmi_callerid: str | None = None
    telecmi_recording_base_url: str | None = None
    public_base_url: str | None = None
    meta_page_token: str | None = None
    meta_verify_token: str | None = None
    meta_ig_user_id: str | None = None
    meta_access_token: str | None = None
    meta_phone_number_id: str | None = None
    meta_app_id: str | None = None
    telegram_bot_token: str | None = None
    instagram_access_token: str | None = None
    instagram_page_id: str | None = None
    facebook_access_token: str | None = None
    facebook_page_id: str | None = None
    meta_app_secret: str | None = None
    sentry_dsn: str | None = None
    vapid_public_key: str | None = None
    vapid_private_key: str | None = None
    vapid_subject: str | None = None

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}

    @model_validator(mode="after")
    def _warn_missing_secrets(self) -> "Settings":
        critical = {
            "sarvam_api_key": "WhatsApp AI replies, call transcription, and knowledge image OCR will fail",
            "gemini_api_key": "WhatsApp AI voice replies will fail",
            "groq_api_key": "Scoring, call summaries, AI tuning, lead briefs, and conversation compaction will fail",
            "meta_app_secret": "Webhook signature verification will reject all inbound",
            "jina_api_key": "Knowledge base RAG embeddings will fail",
        }
        for key, impact in critical.items():
            if not getattr(self, key):
                logger.warning("Missing %s — %s", key, impact)
        return self


settings = Settings()
