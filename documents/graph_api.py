"""
문서 그래프 생성 전용 API
LightRAG 기반 문서 업로드부터 GraphDB 생성까지의 핵심 기능만 포함
"""

import os
import hashlib
import asyncio
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

from services.graph_service import get_graph_service, DocumentData, cleanup_graph_service

# FastAPI 앱 생성
app = FastAPI(
    title="문서 그래프 생성 API",
    description="LightRAG 기반 문서 업로드부터 GraphDB 생성까지의 API",
    version="1.0.0"
)

# 업로드 디렉터리 설정
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 저장된 문서들을 메모리에서 관리 (간단한 구현)
documents_store: Dict[str, Dict[str, Any]] = {}


# API 모델들
class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    file_size: int
    status: str
    message: str


class GraphCreationRequest(BaseModel):
    content: str
    doc_id: Optional[str] = None
    file_path: Optional[str] = "text_input"


class QueryRequest(BaseModel):
    query: str
    mode: str = "hybrid"


class KnowledgeGraphRequest(BaseModel):
    node_label: str
    max_depth: int = 3
    max_nodes: int = 100


def calculate_file_hash(content: bytes) -> str:
    """파일 해시 계산"""
    return hashlib.sha256(content).hexdigest()


def clean_text(text: str) -> str:
    """텍스트 정리"""
    return text.strip().replace("\\x00", "")


# API 엔드포인트들
@app.get("/")
def root():
    """루트 엔드포인트"""
    return {
        "message": "문서 그래프 생성 API",
        "status": "running",
        "features": [
            "문서 업로드",
            "텍스트 직접 입력",
            "그래프 생성 (LightRAG 기반)",
            "지식 그래프 조회",
            "질의 응답"
        ]
    }


@app.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """
    문서 파일 업로드
    """
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="파일명이 없습니다")
        
        # 파일 내용 읽기
        content = await file.read()
        
        # 텍스트 파일만 지원 (간단한 구현)
        if not file.filename.endswith(('.txt', '.md')):
            raise HTTPException(status_code=400, detail="현재 .txt, .md 파일만 지원됩니다")
        
        try:
            text_content = content.decode('utf-8')
        except UnicodeDecodeError:
            try:
                text_content = content.decode('cp949')  # 한글 인코딩 시도
            except UnicodeDecodeError:
                raise HTTPException(status_code=400, detail="UTF-8 또는 CP949로 디코딩할 수 없는 파일입니다")
        
        # 파일 저장
        file_hash = calculate_file_hash(content)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{timestamp}_{file.filename}"\n        file_path = Path(UPLOAD_DIR) / safe_filename
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(text_content)
        
        # 문서 정보 저장
        document_id = f"doc_{file_hash[:12]}"
        document_info = {
            "document_id": document_id,
            "filename": file.filename,
            "safe_filename": safe_filename,
            "file_path": str(file_path),
            "file_size": len(content),
            "content": clean_text(text_content),
            "file_hash": file_hash,
            "uploaded_at": datetime.now().isoformat(),
            "graph_created": False
        }
        
        documents_store[document_id] = document_info
        
        return DocumentUploadResponse(
            document_id=document_id,
            filename=file.filename,
            file_size=len(content),
            status="uploaded",
            message="파일이 성공적으로 업로드되었습니다"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"업로드 실패: {str(e)}")


@app.post("/create_from_text")
async def create_from_text(request: GraphCreationRequest):
    """
    텍스트 직접 입력으로 그래프 생성
    """
    try:
        # 문서 ID 생성
        content_hash = calculate_file_hash(request.content.encode('utf-8'))
        document_id = request.doc_id or f"text_{content_hash[:12]}"
        
        # 문서 정보 저장
        document_info = {
            "document_id": document_id,
            "filename": "text_input",
            "content": clean_text(request.content),
            "file_path": request.file_path,
            "created_at": datetime.now().isoformat(),
            "graph_created": False
        }
        
        documents_store[document_id] = document_info
        
        # 즉시 그래프 생성
        result = await create_graph_for_document(document_id)
        
        return {
            "status": "success",
            "message": "텍스트로부터 그래프가 생성되었습니다",
            "document_id": document_id,
            "graph_result": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"텍스트 처리 실패: {str(e)}")


async def create_graph_for_document(document_id: str) -> Dict[str, Any]:
    """
    문서에 대한 그래프 생성 (내부 함수)
    """
    if document_id not in documents_store:
        raise ValueError(f"문서를 찾을 수 없습니다: {document_id}")
    
    doc_info = documents_store[document_id]
    
    # GraphService 인스턴스 가져오기
    graph_service = await get_graph_service(workspace=f"graph_{document_id}")
    
    # 문서 데이터 생성
    document_data = DocumentData(
        content=doc_info["content"],
        doc_id=document_id,
        file_path=doc_info.get("file_path", "unknown")
    )
    
    # 그래프 처리 실행
    result = await graph_service.process_document(document_data)
    
    if result.success:
        # 그래프 생성 성공시 문서 정보 업데이트
        documents_store[document_id]["graph_created"] = True
        documents_store[document_id]["graph_result"] = {
            "chunks_created": result.chunks_created,
            "entities_extracted": result.entities_extracted,
            "relations_extracted": result.relations_extracted,
            "groups_processed": result.groups_processed,
            "processing_time": result.processing_time
        }
    
    return {
        "success": result.success,
        "message": result.message,
        "chunks_created": result.chunks_created,
        "entities_extracted": result.entities_extracted,
        "relations_extracted": result.relations_extracted,
        "groups_processed": result.groups_processed,
        "processing_time": result.processing_time,
        "error": result.error
    }


@app.post("/documents/{document_id}/create_graph")
async def create_graph(document_id: str):
    """
    업로드된 문서의 그래프 생성
    """
    try:
        result = await create_graph_for_document(document_id)
        
        if result["success"]:
            return {
                "status": "success",
                "message": "그래프가 성공적으로 생성되었습니다",
                "data": result
            }
        else:
            return {
                "status": "error",
                "message": result["message"],
                "error": result["error"]
            }
            
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"그래프 생성 실패: {str(e)}")


@app.get("/documents/{document_id}/labels")
async def get_graph_labels(document_id: str):
    """
    문서의 그래프 라벨 조회
    """
    try:
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")
        
        doc_info = documents_store[document_id]
        if not doc_info.get("graph_created", False):
            raise HTTPException(status_code=400, detail="먼저 그래프를 생성해주세요")
        
        graph_service = await get_graph_service(workspace=f"graph_{document_id}")
        labels = await graph_service.get_graph_labels()
        
        return {
            "status": "success",
            "data": {
                "document_id": document_id,
                "labels": labels,
                "label_count": len(labels)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"라벨 조회 실패: {str(e)}")


@app.post("/documents/{document_id}/knowledge_graph")
async def get_knowledge_graph(document_id: str, request: KnowledgeGraphRequest):
    """
    특정 노드를 중심으로 한 지식 그래프 조회
    """
    try:
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")
        
        doc_info = documents_store[document_id]
        if not doc_info.get("graph_created", False):
            raise HTTPException(status_code=400, detail="먼저 그래프를 생성해주세요")
        
        graph_service = await get_graph_service(workspace=f"graph_{document_id}")
        kg = await graph_service.get_knowledge_graph(
            node_label=request.node_label,
            max_depth=request.max_depth,
            max_nodes=request.max_nodes
        )
        
        if kg:
            return {
                "status": "success",
                "data": {
                    "document_id": document_id,
                    "node_label": request.node_label,
                    "knowledge_graph": kg
                }
            }
        else:
            return {
                "status": "error",
                "message": "지식 그래프를 찾을 수 없습니다"
            }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"지식 그래프 조회 실패: {str(e)}")


@app.post("/documents/{document_id}/query")
async def query_graph(document_id: str, request: QueryRequest):
    """
    문서의 그래프에 질의
    """
    try:
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")
        
        doc_info = documents_store[document_id]
        if not doc_info.get("graph_created", False):
            raise HTTPException(status_code=400, detail="먼저 그래프를 생성해주세요")
        
        graph_service = await get_graph_service(workspace=f"graph_{document_id}")
        answer = await graph_service.query_knowledge(request.query, request.mode)
        
        return {
            "status": "success",
            "data": {
                "document_id": document_id,
                "query": request.query,
                "mode": request.mode,
                "answer": answer
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"질의 실패: {str(e)}")


@app.get("/documents")
def list_documents():
    """
    업로드된 문서 목록 조회
    """
    documents = []
    for doc_id, doc_info in documents_store.items():
        documents.append({
            "document_id": doc_id,
            "filename": doc_info.get("filename", "unknown"),
            "graph_created": doc_info.get("graph_created", False),
            "uploaded_at": doc_info.get("uploaded_at"),
            "graph_result": doc_info.get("graph_result")
        })
    
    return {
        "status": "success",
        "data": {
            "documents": documents,
            "count": len(documents)
        }
    }


@app.get("/documents/{document_id}")
def get_document(document_id: str):
    """
    문서 정보 조회
    """
    if document_id not in documents_store:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")
    
    doc_info = documents_store[document_id]
    
    return {
        "status": "success",
        "data": doc_info
    }


@app.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    """
    문서 삭제
    """
    try:
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")
        
        doc_info = documents_store[document_id]
        
        # 파일 삭제
        if "file_path" in doc_info:
            file_path = Path(doc_info["file_path"])
            if file_path.exists():
                file_path.unlink()
        
        # 그래프 데이터 삭제
        if doc_info.get("graph_created", False):
            graph_service = await get_graph_service(workspace=f"graph_{document_id}")
            await graph_service.delete_document(document_id)
        
        # 메모리에서 삭제
        del documents_store[document_id]
        
        return {
            "status": "success",
            "message": "문서가 성공적으로 삭제되었습니다"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문서 삭제 실패: {str(e)}")


@app.on_event("shutdown")
async def shutdown_event():
    """
    애플리케이션 종료시 그래프 서비스 정리
    """
    await cleanup_graph_service()


if __name__ == "__main__":
    print("🌟 문서 그래프 생성 API 서버 시작")
    print("📝 API 문서: http://localhost:8001/docs")
    print("🔗 기능:")
    print("   - 문서 업로드: POST /upload")
    print("   - 텍스트 입력: POST /create_from_text")
    print("   - 그래프 생성: POST /documents/{document_id}/create_graph")
    print("   - 그래프 조회: GET /documents/{document_id}/labels")
    print("   - 질의 응답: POST /documents/{document_id}/query")
    
    uvicorn.run(
        "graph_api:app",
        host="0.0.0.0",
        port=8001,
        reload=True
    )