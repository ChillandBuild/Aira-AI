from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str
    supabase_service_key: str
    supabase_jwt_secret: str | None = None
    groq_api_key: str | None = None
    jina_api_key: str | None = None
    telecmi_user_id: str | None = None
    telecmi_secret: str | None = None
    telecmi_callerid: str | None = None
    telecmi_recording_base_url: str | None = None
    public_base_url: str | None = None
    meta_page_token: str | None = None
    meta_verify_token: str | None = None
    meta_ig_user_id: str | None = None
    meta_access_token: str | None = None
    meta_phone_number_id: str | None = None
    telegram_bot_token: str | None = None
    instagram_access_token: str | None = None
    instagram_page_id: str | None = None
    facebook_access_token: str | None = None
    facebook_page_id: str | None = None
    meta_app_secret: str | None = None
    sentry_dsn: str | None = None

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}


settings = Settings()
