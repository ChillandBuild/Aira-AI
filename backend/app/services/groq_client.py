# backend/app/services/groq_client.py
from groq import Groq, AsyncGroq
from app.config_dynamic import get_setting
from app.config import settings

def get_groq_client(tenant_id: str | None = None, is_async: bool = True):
    api_key = get_setting("groq_api_key", tenant_id=tenant_id) or settings.groq_api_key
    if not api_key:
        raise RuntimeError("Groq API key not configured")
    return AsyncGroq(api_key=api_key) if is_async else Groq(api_key=api_key)
