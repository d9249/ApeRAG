"""
Document processing tasks
현재 LightRAG 기반 실제 그래프 생성 로직 포함
"""
import os
import hashlib
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from worker import celery_app
from database import SessionLocal, Document, ProcessingTask, DocumentStatus
from services.graph_service import GraphService, DocumentData, GraphProcessingResult


def process_graph_indexing_sync(document_id: str, content: str, file_path: str) -> Dict[str, Any]:
    """
    동기적으로 그래프 인덱싱 처리 (Celery에서 호출용)
    """
    async def _async_process():
        graph_service = None
        try:
            # GraphService 인스턴스 생성 및 초기화
            graph_service = GraphService(workspace=f"doc_processing_{document_id}")
            success = await graph_service.initialize()
            
            if not success:
                return {
                    "success": False,
                    "error": "GraphService 초기화 실패",
                    "chunks_created": 0,
                    "entities_extracted": 0,
                    "relations_extracted": 0,
                    "groups_processed": 0
                }
            
            # 문서 데이터 생성
            document_data = DocumentData(
                content=content,
                doc_id=document_id,
                file_path=file_path
            )
            
            # 그래프 처리 실행
            result = await graph_service.process_document(document_data)
            
            return {
                "success": result.success,
                "error": result.error,
                "chunks_created": result.chunks_created,
                "entities_extracted": result.entities_extracted,
                "relations_extracted": result.relations_extracted,
                "groups_processed": result.groups_processed
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "chunks_created": 0,
                "entities_extracted": 0,
                "relations_extracted": 0,
                "groups_processed": 0
            }
        finally:
            if graph_service:
                await graph_service.finalize()
    
    # 비동기 함수를 동기적으로 실행
    try:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(_async_process())
    except RuntimeError:
        # 새 이벤트 루프 생성
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_async_process())
        finally:
            loop.close()


@celery_app.task(bind=True)
def parse_document_task(self, document_id: int) -> Dict[str, Any]:
    """
    Parse document content using available parsers
    """
    db = SessionLocal()
    document = None
    try:
        # Get document from database
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise ValueError(f"Document with id {document_id} not found")
        
        # Update document status using query.update()
        db.query(Document).filter(Document.id == document_id).update(
            {"status": DocumentStatus.PARSING}
        )
        db.commit()
        
        # Simulate document parsing (replace with actual parsing logic)
        file_path_str = str(document.file_path)  # Convert Column to string
        file_path = Path(file_path_str)
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
        
        # Update document with parsed content using query.update()
        db.query(Document).filter(Document.id == document_id).update({
            "parsed_content": content,
            "parsed_metadata": metadata,
            "status": DocumentStatus.PARSED,
            "parsed_at": datetime.utcnow()
        })
        db.commit()
        
        return {
            "status": "success",
            "document_id": document_id,
            "content_length": len(content),
            "metadata": metadata
        }
        
    except Exception as e:
        # Update document status to failed
        if document:
            db.query(Document).filter(Document.id == document_id).update(
                {"status": DocumentStatus.FAILED}
            )
            db.commit()
        raise e
    finally:
        db.close()


@celery_app.task(bind=True)
def index_document_task(self, document_id: int, index_types: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Index document in vector store, elasticsearch, etc.
    이제 실제 LightRAG 기반 그래프 생성 로직 포함
    """
    if index_types is None:
        index_types = ["vector", "fulltext"]
    
    db = SessionLocal()
    document = None
    try:
        # Get document from database
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise ValueError(f"Document with id {document_id} not found")
        
        if not document.parsed_content:
            raise ValueError(f"Document {document_id} has not been parsed yet")
        
        # Update document status
        db.query(Document).filter(Document.id == document_id).update(
            {"status": DocumentStatus.INDEXING}
        )
        db.commit()
        
        results = {}
        
        # Vector indexing
        if "vector" in index_types:
            # Placeholder for vector indexing
            results["vector"] = {"status": "indexed", "vectors": 10}
            db.query(Document).filter(Document.id == document_id).update(
                {"vector_indexed": True}
            )
        
        # Full-text indexing
        if "fulltext" in index_types:
            # Placeholder for elasticsearch indexing
            results["fulltext"] = {"status": "indexed", "index": "documents"}
            db.query(Document).filter(Document.id == document_id).update(
                {"fulltext_indexed": True}
            )
        
        # Graph indexing - 실제 LightRAG 기반 구현
        if "graph" in index_types:
            graph_result = process_graph_indexing_sync(
                document_id=str(document_id),
                content=str(document.parsed_content),  # Convert Column to string
                file_path=str(document.original_filename)  # Convert Column to string
            )
            
            if graph_result["success"]:
                results["graph"] = {
                    "status": "indexed",
                    "chunks_created": graph_result["chunks_created"],
                    "entities_extracted": graph_result["entities_extracted"],
                    "relations_extracted": graph_result["relations_extracted"],
                    "groups_processed": graph_result["groups_processed"]
                }
                db.query(Document).filter(Document.id == document_id).update(
                    {"graph_indexed": True}
                )
            else:
                results["graph"] = {
                    "status": "failed",
                    "error": graph_result["error"]
                }
                # 그래프 인덱싱 실패시에도 다른 인덱싱은 성공으로 처리
        
        # Update document status
        db.query(Document).filter(Document.id == document_id).update(
            {"status": DocumentStatus.INDEXED, "indexed_at": datetime.utcnow()}
        )
        db.commit()
        
        return {
            "status": "success",
            "document_id": document_id,
            "results": results
        }
        
    except Exception as e:
        # Update document status to failed
        if document:
            db.query(Document).filter(Document.id == document_id).update(
                {"status": DocumentStatus.FAILED}
            )
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
        
        # Step 2: Index document (including graph indexing)
        index_result = index_document_task.apply_async(args=[document_id, ["vector", "fulltext", "graph"]])
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