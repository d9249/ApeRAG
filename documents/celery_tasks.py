"""
Document processing tasks
"""
import os
import hashlib
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

from worker import celery_app
from database import SessionLocal, Document, ProcessingTask, DocumentStatus


@celery_app.task(bind=True)
def parse_document_task(self, document_id: int) -> Dict[str, Any]:
    """
    Parse document content using available parsers
    """
    db = SessionLocal()
    try:
        # Get document from database
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise ValueError(f"Document with id {document_id} not found")
        
        # Update document status
        document.status = DocumentStatus.PARSING
        db.commit()
        
        # Simulate document parsing (replace with actual parsing logic)
        file_path = Path(document.file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Read file content (simplified)
        content = ""
        metadata = {}
        
        if file_path.suffix.lower() == '.txt':
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                metadata = {"pages": 1, "words": len(content.split())}
        elif file_path.suffix.lower() == '.pdf':
            # Placeholder for PDF parsing
            content = f"PDF content from {file_path.name}"
            metadata = {"pages": 1, "words": len(content.split())}
        else:
            # Generic handling
            content = f"Content from {file_path.name}"
            metadata = {"type": file_path.suffix, "size": file_path.stat().st_size}
        
        # Update document with parsed content
        document.parsed_content = content
        document.parsed_metadata = metadata
        document.status = DocumentStatus.PARSED
        document.parsed_at = datetime.utcnow()
        db.commit()
        
        return {
            "status": "success",
            "document_id": document_id,
            "content_length": len(content),
            "metadata": metadata
        }
        
    except Exception as e:
        # Update document status to failed
        document.status = DocumentStatus.FAILED
        db.commit()
        raise e
    finally:
        db.close()


@celery_app.task(bind=True)
def index_document_task(self, document_id: int, index_types: List[str] = None) -> Dict[str, Any]:
    """
    Index document in vector store, elasticsearch, etc.
    """
    if index_types is None:
        index_types = ["vector", "fulltext"]
    
    db = SessionLocal()
    try:
        # Get document from database
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise ValueError(f"Document with id {document_id} not found")
        
        if not document.parsed_content:
            raise ValueError(f"Document {document_id} has not been parsed yet")
        
        # Update document status
        document.status = DocumentStatus.INDEXING
        db.commit()
        
        results = {}
        
        # Vector indexing
        if "vector" in index_types:
            # Placeholder for vector indexing
            results["vector"] = {"status": "indexed", "vectors": 10}
            document.vector_indexed = True
        
        # Full-text indexing
        if "fulltext" in index_types:
            # Placeholder for elasticsearch indexing
            results["fulltext"] = {"status": "indexed", "index": "documents"}
            document.fulltext_indexed = True
        
        # Graph indexing
        if "graph" in index_types:
            # Placeholder for graph indexing
            results["graph"] = {"status": "indexed", "nodes": 5, "edges": 8}
            document.graph_indexed = True
        
        # Update document status
        document.status = DocumentStatus.INDEXED
        document.indexed_at = datetime.utcnow()
        db.commit()
        
        return {
            "status": "success",
            "document_id": document_id,
            "results": results
        }
        
    except Exception as e:
        # Update document status to failed
        document.status = DocumentStatus.FAILED
        db.commit()
        raise e
    finally:
        db.close()


@celery_app.task(bind=True)
def process_document_workflow(self, document_id: int) -> Dict[str, Any]:
    """
    Complete document processing workflow: parse -> index
    """
    try:
        # Step 1: Parse document
        parse_result = parse_document_task.apply_async(args=[document_id])
        parse_result.get()  # Wait for completion
        
        # Step 2: Index document
        index_result = index_document_task.apply_async(args=[document_id])
        index_result.get()  # Wait for completion
        
        return {
            "status": "success",
            "document_id": document_id,
            "workflow": "completed"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "document_id": document_id,
            "error": str(e)
        }