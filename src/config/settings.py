from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    # Application
    app_name: str = "AccountantAI"
    app_env: str = "development"
    debug: bool = True
    secret_key: str
    
    # Database
    database_url: str
    redis_url: Optional[str] = None
    
    # Gmail API
    gmail_client_id: str
    gmail_client_secret: str
    gmail_redirect_uri: str = "http://localhost:8000/auth/gmail/callback"
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
    fiken_redirect_uri: str = "http://localhost:8000/auth/fiken/callback"
    fiken_api_url: str = "https://api.fiken.no/api/v2"
    fiken_company_id: str
    
    # Receipt processing
    receipt_email_filter: str = "invoice,receipt,faktura,kvittering"
    receipt_check_interval: int = 300  # seconds
    
    # File handling
    upload_folder: str = "./uploads"
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