"""
Document Processing Pipeline API
"""
import os
import hashlib
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db, init_db, Document, Collection, ProcessingTask, DocumentStatus
from celery_tasks import parse_document_task, index_document_task, process_document_workflow
from settings import settings, UPLOAD_DIR

# Initialize database on startup
init_db()

# Create FastAPI app
app = FastAPI(
    title="Document Processing Pipeline API",
    description="API for document upload, parsing, and indexing",
    version="1.0.0"
)


# Pydantic models
class DocumentResponse(BaseModel):
    id: int
    filename: str
    original_filename: str
    file_size: int
    mime_type: str
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class TaskResponse(BaseModel):
    task_id: str
    status: str
    document_id: int


class ProcessingStatus(BaseModel):
    document_id: int
    status: str
    parsed: bool
    vector_indexed: bool
    fulltext_indexed: bool
    graph_indexed: bool


# Utility functions
def calculate_file_hash(file_path: Path) -> str:
    """Calculate SHA-256 hash of file"""
    hash_sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()


def get_mime_type(filename: str) -> str:
    """Get MIME type based on file extension"""
    extension = Path(filename).suffix.lower()
    mime_types = {
        '.txt': 'text/plain',
        '.pdf': 'application/pdf',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
    }
    return mime_types.get(extension, 'application/octet-stream')


# API endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow()}


@app.post("/documents/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    collection_id: Optional[int] = None,
    auto_process: bool = True,
    db: Session = Depends(get_db)
):
    """
    Upload a document for processing
    """
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")
        
        # Create upload directory if it doesn't exist
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        
        # Generate unique filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        file_extension = Path(file.filename).suffix
        unique_filename = f"{timestamp}_{file.filename}"
        file_path = Path(UPLOAD_DIR) / unique_filename
        
        # Save file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Calculate file hash
        file_hash = calculate_file_hash(file_path)
        file_size = file_path.stat().st_size
        mime_type = get_mime_type(file.filename)
        
        # Check for duplicate
        existing_doc = db.query(Document).filter(Document.file_hash == file_hash).first()
        if existing_doc:
            # Remove the uploaded file since it's a duplicate
            file_path.unlink()
            return existing_doc
        
        # Create document record
        document = Document(
            filename=unique_filename,
            original_filename=file.filename,
            file_path=str(file_path),
            file_size=file_size,
            mime_type=mime_type,
            file_hash=file_hash,
            status=DocumentStatus.UPLOADED,
            doc_metadata={"collection_id": collection_id} if collection_id else {}
        )
        
        db.add(document)
        db.commit()
        db.refresh(document)
        
        # Start processing if requested
        if auto_process:
            task = process_document_workflow.delay(document.id)
            
            # Create task record
            processing_task = ProcessingTask(
                document_id=document.id,
                task_type="workflow",
                task_id=task.id,
                status="pending"
            )
            db.add(processing_task)
            db.commit()
        
        return document
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.get("/documents", response_model=List[DocumentResponse])
async def list_documents(
    skip: int = 0,
    limit: int = 10,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    List documents with optional filtering
    """
    query = db.query(Document)
    
    if status:
        query = query.filter(Document.status == status)
    
    documents = query.offset(skip).limit(limit).all()
    return documents


@app.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: int, db: Session = Depends(get_db)):
    """
    Get document by ID
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@app.get("/documents/{document_id}/status", response_model=ProcessingStatus)
async def get_document_status(document_id: int, db: Session = Depends(get_db)):
    """
    Get document processing status
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return ProcessingStatus(
        document_id=document.id,
        status=document.status.value,
        parsed=document.parsed_content is not None,
        vector_indexed=document.vector_indexed,
        fulltext_indexed=document.fulltext_indexed,
        graph_indexed=document.graph_indexed
    )


@app.post("/documents/{document_id}/parse", response_model=TaskResponse)
async def parse_document(document_id: int, db: Session = Depends(get_db)):
    """
    Trigger document parsing
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Start parsing task
    task = parse_document_task.delay(document_id)
    
    # Create task record
    processing_task = ProcessingTask(
        document_id=document_id,
        task_type="parsing",
        task_id=task.id,
        status="pending"
    )
    db.add(processing_task)
    db.commit()
    
    return TaskResponse(
        task_id=task.id,
        status="pending",
        document_id=document_id
    )


@app.post("/documents/{document_id}/index", response_model=TaskResponse)
async def index_document(
    document_id: int, 
    index_types: List[str] = ["vector", "fulltext"],
    db: Session = Depends(get_db)
):
    """
    Trigger document indexing
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Start indexing task
    task = index_document_task.delay(document_id, index_types)
    
    # Create task record
    processing_task = ProcessingTask(
        document_id=document_id,
        task_type="indexing",
        task_id=task.id,
        status="pending"
    )
    db.add(processing_task)
    db.commit()
    
    return TaskResponse(
        task_id=task.id,
        status="pending",
        document_id=document_id
    )


@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str, db: Session = Depends(get_db)):
    """
    Get task status
    """
    task = db.query(ProcessingTask).filter(ProcessingTask.task_id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {
        "task_id": task_id,
        "status": task.status,
        "progress": task.progress,
        "error_message": task.error_message,
        "result": task.result,
        "created_at": task.created_at,
        "updated_at": task.updated_at
    }


@app.delete("/documents/{document_id}")
async def delete_document(document_id: int, db: Session = Depends(get_db)):
    """
    Delete document and its file
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Delete file
    file_path = Path(document.file_path)
    if file_path.exists():
        file_path.unlink()
    
    # Delete database record
    db.delete(document)
    db.commit()
    
    return {"message": "Document deleted successfully"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host=settings.api_host, 
        port=settings.api_port, 
        reload=settings.debug
    )