"""
Database initialization and models for Document Processing Pipeline
"""
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, JSON, Enum, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func
from datetime import datetime
import enum
from settings import SQLALCHEMY_DATABASE_URL

# Create database engine
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class DocumentStatus(enum.Enum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    INDEXING = "indexing"
    INDEXED = "indexed"
    FAILED = "failed"


class Document(Base):
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String, nullable=False)
    file_hash = Column(String, nullable=False, index=True)
    
    status = Column(Enum(DocumentStatus), default=DocumentStatus.UPLOADED)
    
    # Document metadata
    doc_metadata = Column(JSON, default={})
    
    # Parsing results
    parsed_content = Column(Text, nullable=True)
    parsed_metadata = Column(JSON, default={})
    
    # Indexing status
    vector_indexed = Column(Boolean, default=False)
    fulltext_indexed = Column(Boolean, default=False)
    graph_indexed = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    parsed_at = Column(DateTime(timezone=True), nullable=True)
    indexed_at = Column(DateTime(timezone=True), nullable=True)


class Collection(Base):
    __tablename__ = "collections"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(Text, nullable=True)
    
    # Configuration
    config = Column(JSON, default={})
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ProcessingTask(Base):
    __tablename__ = "processing_tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, nullable=False, index=True)
    task_type = Column(String, nullable=False)  # 'parsing', 'indexing', etc.
    task_id = Column(String, nullable=False, index=True)  # Celery task ID
    status = Column(String, nullable=False, default="pending")
    
    # Task details
    progress = Column(Integer, default=0)  # 0-100
    error_message = Column(Text, nullable=True)
    result = Column(JSON, default={})
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Initialize database
def init_db():
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    print("Creating database tables...")
    init_db()
    print("Database tables created successfully!")