import os
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def load_env():
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()

load_env()

class Settings(BaseSettings):
    PROJECT_NAME: str = "Secure Multi-Modal RAG System API"
    VERSION: str = "1.0.0"
    DEBUG: bool = os.environ.get("DEBUG", "false").lower() in ("true", "1", "yes")
    ENVIRONMENT: str = os.environ.get("ENVIRONMENT", "development")
    ALLOWED_ORIGINS: list = [origin.strip() for origin in os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()]
    
    JWT_SECRET_KEY: str = os.environ.get("JWT_SECRET_KEY", "secure_rag_super_secret_jwt_key_2026_change_in_prod")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 8
    
    POSTGRES_HOST: str = os.environ.get("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: str = os.environ.get("POSTGRES_PORT", "5432")
    POSTGRES_DB: str = os.environ.get("POSTGRES_DB", "RAG_System")
    POSTGRES_USER: str = os.environ.get("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.environ.get("POSTGRES_PASSWORD", "postgres")
    
    QDRANT_URL: str = os.environ.get("QDRANT_URL", "")
    QDRANT_API_KEY: str = os.environ.get("QDRANT_API_KEY", "")
    QDRANT_COLLECTION: str = os.environ.get("QDRANT_COLLECTION", "secure_rag_chunks")
    
    OLLAMA_URL: str = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    EMBEDDING_MODEL: str = os.environ.get("EMBEDDING_MODEL", "embeddinggemma:300m")
    GEN_MODEL: str = os.environ.get("GEN_MODEL", "gemma3:1b")
    
    # Upload & Ingestion settings
    MAX_UPLOAD_SIZE_MB: int = int(os.environ.get("MAX_UPLOAD_SIZE_MB", 20))
    MAX_PDF_PAGES: int = int(os.environ.get("MAX_PDF_PAGES", 50))
    UPLOAD_DIR: str = os.path.join(BASE_DIR, "dataset", "uploads")
    ALLOWED_EXTENSIONS: set = {".pdf", ".png", ".jpg", ".jpeg"}

    # Rate Limiting configuration
    RATE_LIMIT_ENABLED: bool = os.environ.get("RATE_LIMIT_ENABLED", "true").lower() in ("true", "1", "yes")
    RATE_LIMIT_WINDOW_SECONDS: int = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", 60))
    RATE_LIMIT_LOGIN: int = int(os.environ.get("RATE_LIMIT_LOGIN", 10))
    RATE_LIMIT_CHAT: int = int(os.environ.get("RATE_LIMIT_CHAT", 30))
    RATE_LIMIT_UPLOAD: int = int(os.environ.get("RATE_LIMIT_UPLOAD", 10))
    RATE_LIMIT_API: int = int(os.environ.get("RATE_LIMIT_API", 120))
    RATE_LIMIT_ADMIN: int = int(os.environ.get("RATE_LIMIT_ADMIN", 60))

    model_config = SettingsConfigDict(extra="ignore")

settings = Settings()
