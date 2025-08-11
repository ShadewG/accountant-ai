from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    # Application (with defaults, not required in env)
    app_name: str = "AccountantAI"
    app_env: str = os.getenv("RAILWAY_ENVIRONMENT", "development")
    debug: bool = False
    secret_key: str = os.getenv("SECRET_KEY", "default-dev-secret-" + os.urandom(8).hex())
    
    # Database
    database_url: str
    redis_url: Optional[str] = None
    
    # Gmail API (optional - only if using email features)
    gmail_client_id: Optional[str] = None
    gmail_client_secret: Optional[str] = None
    gmail_redirect_uri: str = os.getenv("RAILWAY_STATIC_URL", "http://localhost:8000") + "/auth/gmail/callback"
    gmail_scopes: list = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.modify"
    ]
    
    # OpenAI
    openai_api_key: str
    openai_model: str = "gpt-4-vision-preview"
    
    # Folio.no API
    folio_session_cookie: str
    folio_org_number: str
    
    # Fiken API
    fiken_client_id: str
    fiken_client_secret: str
    fiken_redirect_uri: str = os.getenv("RAILWAY_STATIC_URL", "http://localhost:8000") + "/auth/fiken/callback"
    fiken_api_url: str = "https://api.fiken.no/api/v2"
    fiken_company_id: Optional[str] = None  # Can be set later in Fiken
    
    # Receipt processing
    receipt_email_filter: str = "invoice,receipt,faktura,kvittering"
    receipt_check_interval: int = 300  # seconds
    
    # File handling (with Railway-aware defaults)
    upload_folder: str = "/app/uploads" if os.getenv("RAILWAY_ENVIRONMENT") else "./uploads"
    max_file_size: int = 10485760  # 10MB
    allowed_extensions: set = {
        'pdf', 'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'
    }
    
    # Logging
    log_level: str = "INFO"
    sentry_dsn: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()