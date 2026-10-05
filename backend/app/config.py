import os
from pydantic_settings import BaseSettings

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
    
    class Config:
        extra = "ignore"

settings = Settings()
