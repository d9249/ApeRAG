"""
Document Processing Pipeline Configuration
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/doc_pipeline"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_database: str = "doc_pipeline"
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    
    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_url: str = "http://localhost:6333"
    
    # Elasticsearch
    elasticsearch_host: str = "localhost"
    elasticsearch_port: int = 9200
    elasticsearch_url: str = "http://localhost:9200"
    
    # Application
    environment: str = "development"
    debug: bool = True
    log_level: str = "INFO"
    shared_data_path: str = "/shared"
    upload_path: str = "/app/uploads"
    
    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings()


# Database configuration
SQLALCHEMY_DATABASE_URL = settings.database_url

# Redis configuration
REDIS_URL = settings.redis_url

# Vector store configuration
QDRANT_CONFIG = {
    "host": settings.qdrant_host,
    "port": settings.qdrant_port,
    "url": settings.qdrant_url
}

# Elasticsearch configuration
ELASTICSEARCH_CONFIG = {
    "host": settings.elasticsearch_host,
    "port": settings.elasticsearch_port,
    "url": settings.elasticsearch_url
}

# File paths
UPLOAD_DIR = settings.upload_path
SHARED_DATA_DIR = settings.shared_data_path

# Ensure upload directory exists
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(SHARED_DATA_DIR, exist_ok=True)