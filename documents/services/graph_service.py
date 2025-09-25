"""
그래프 생성 서비스 - LightRAG 기반 모듈화된 그래프 생성 로직
다른 API에서 재사용 가능하도록 설계
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from pathlib import Path
import sys
import os

# LightRAG 모듈 import
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from aperag.graph.lightrag import LightRAG
from aperag.graph.lightrag.base import QueryParam
from aperag.graph.lightrag.utils import EmbeddingFunc
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class GraphProcessingResult:
    """그래프 처리 결과"""
    success: bool
    message: str
    document_id: Optional[str] = None
    chunks_created: int = 0
    entities_extracted: int = 0
    relations_extracted: int = 0
    groups_processed: int = 0
    processing_time: Optional[float] = None
    error: Optional[str] = None


@dataclass
class DocumentData:
    """문서 데이터"""
    content: str
    doc_id: str
    file_path: str = "unknown_source"


class GraphService:
    """
    그래프 생성 서비스
    
    LightRAG를 사용하여 문서에서 엔티티/관계를 추출하고 지식 그래프를 생성하는
    모듈화된 서비스. 다른 API에서 재사용 가능하도록 설계됨.
    """
    
    def __init__(self, 
                 workspace: str = "graph_service",
                 embedding_func: Optional[EmbeddingFunc] = None,
                 llm_model_func: Optional[callable] = None,
                 chunk_token_size: int = 1200,
                 chunk_overlap_token_size: int = 100):
        """
        그래프 서비스 초기화
        
        Args:
            workspace: 워크스페이스 이름 (데이터 격리용)
            embedding_func: 임베딩 함수
            llm_model_func: LLM 함수
            chunk_token_size: 청크 크기 (토큰 단위)
            chunk_overlap_token_size: 청크 중복 크기 (토큰 단위)
        """
        self.workspace = workspace
        self.lightrag_instance: Optional[LightRAG] = None
        self.is_initialized = False
        
        # 기본 함수들 설정 (실제 구현시 교체)
        self.embedding_func = embedding_func or self._create_default_embedding_func()
        self.llm_model_func = llm_model_func or self._create_default_llm_func()
        
        # 청킹 설정 (메모리 규칙에 따라)
        self.chunk_token_size = chunk_token_size
        self.chunk_overlap_token_size = chunk_overlap_token_size
    
    def _create_default_embedding_func(self) -> EmbeddingFunc:
        """기본 임베딩 함수 생성 (더미 구현)"""
        async def dummy_embedding(texts: List[str]) -> np.ndarray:
            # 실제로는 OpenAI 또는 다른 임베딩 서비스 사용
            return np.random.rand(len(texts), 1536).astype(np.float32)
        
        return EmbeddingFunc(
            embedding_dim=1536,
            max_token_size=8192,
            func=dummy_embedding
        )
    
    def _create_default_llm_func(self) -> callable:
        """기본 LLM 함수 생성 (더미 구현)"""
        async def dummy_llm(prompt: str, **kwargs) -> str:
            # 실제로는 OpenAI 또는 다른 LLM 서비스 사용
            return f"[더미 응답] {prompt[:100]}..."
        
        return dummy_llm
    
    async def initialize(self, 
                        kv_storage: str = "PGOpsSyncKVStorage",
                        vector_storage: str = "PGOpsSyncVectorStorage", 
                        graph_storage: str = "PGOpsSyncGraphStorage") -> bool:
        """
        서비스 초기화
        
        Args:
            kv_storage: KV 스토리지 타입
            vector_storage: 벡터 스토리지 타입
            graph_storage: 그래프 스토리지 타입
        
        Returns:
            초기화 성공 여부
        """
        try:
            logger.info(f"GraphService 초기화 시작: workspace={self.workspace}")
            
            # LightRAG 인스턴스 생성
            self.lightrag_instance = LightRAG(
                # 스토리지 설정
                kv_storage=kv_storage,
                vector_storage=vector_storage,
                graph_storage=graph_storage,
                
                # 워크스페이스 설정
                workspace=self.workspace,
                
                # 함수 설정
                embedding_func=self.embedding_func,
                llm_model_func=self.llm_model_func,
                llm_model_name="gpt-4o-mini",
                
                # 청킹 설정 (메모리 규칙 준수)
                chunk_token_size=self.chunk_token_size,
                chunk_overlap_token_size=self.chunk_overlap_token_size,
                
                # 엔티티 추출 설정
                entity_extract_max_gleaning=1,
            )
            
            # 스토리지 초기화
            await self.lightrag_instance.initialize_storages()
            
            self.is_initialized = True
            logger.info("GraphService 초기화 완료")
            return True
            
        except Exception as e:
            logger.error(f"GraphService 초기화 실패: {str(e)}")
            return False
    
    async def finalize(self):
        """서비스 정리"""
        if self.lightrag_instance and self.is_initialized:
            await self.lightrag_instance.finalize_storages()
            self.is_initialized = False
            logger.info("GraphService 정리 완료")
    
    async def process_document(self, document: DocumentData) -> GraphProcessingResult:
        """
        단일 문서 처리 - 청킹부터 그래프 생성까지
        
        Args:
            document: 처리할 문서 데이터
        
        Returns:
            처리 결과
        """
        if not self.is_initialized or not self.lightrag_instance:
            return GraphProcessingResult(
                success=False,
                message="GraphService가 초기화되지 않았습니다",
                error="Service not initialized"
            )
        
        import time
        start_time = time.time()
        
        try:
            logger.info(f"문서 처리 시작: {document.doc_id}")
            
            # 1. 문서 삽입 및 청킹
            chunk_result = await self.lightrag_instance.ainsert_and_chunk_document(
                documents=[document.content],
                doc_ids=[document.doc_id],
                file_paths=[document.file_path]
            )
            
            if chunk_result['status'] != 'success':
                return GraphProcessingResult(
                    success=False,
                    message="문서 청킹 실패",
                    document_id=document.doc_id,
                    error="Chunking failed"
                )
            
            chunks_created = chunk_result['total_chunks']
            logger.info(f"청킹 완료: {chunks_created}개 청크 생성")
            
            # 2. 청크 데이터 수집
            chunk_data = chunk_result['results'][0]['chunks_data']
            
            # 3. 그래프 인덱싱 (엔티티/관계 추출 및 그래프 생성)
            graph_result = await self.lightrag_instance.aprocess_graph_indexing(
                chunks=chunk_data,
                collection_id=document.doc_id
            )
            
            if graph_result['status'] != 'success':
                return GraphProcessingResult(
                    success=False,
                    message="그래프 인덱싱 실패",
                    document_id=document.doc_id,
                    chunks_created=chunks_created,
                    error="Graph indexing failed"
                )
            
            processing_time = time.time() - start_time
            
            logger.info(f"문서 처리 완료: {document.doc_id}")
            logger.info(f"  - 청크: {chunks_created}개")
            logger.info(f"  - 엔티티: {graph_result['entities_extracted']}개")
            logger.info(f"  - 관계: {graph_result['relations_extracted']}개")
            logger.info(f"  - 처리 시간: {processing_time:.2f}초")
            
            return GraphProcessingResult(
                success=True,
                message="문서 처리 완료",
                document_id=document.doc_id,
                chunks_created=chunks_created,
                entities_extracted=graph_result['entities_extracted'],
                relations_extracted=graph_result['relations_extracted'],
                groups_processed=graph_result['groups_processed'],
                processing_time=processing_time
            )
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"문서 처리 실패: {document.doc_id} - {str(e)}")
            
            return GraphProcessingResult(
                success=False,
                message=f"문서 처리 실패: {str(e)}",
                document_id=document.doc_id,
                processing_time=processing_time,
                error=str(e)
            )
    
    async def process_multiple_documents(self, documents: List[DocumentData]) -> List[GraphProcessingResult]:
        """
        여러 문서 일괄 처리
        
        Args:
            documents: 처리할 문서 리스트
        
        Returns:
            처리 결과 리스트
        """
        results = []
        
        for document in documents:
            result = await self.process_document(document)
            results.append(result)
        
        return results
    
    async def get_graph_labels(self) -> List[str]:
        """생성된 엔티티 라벨 조회"""
        if not self.is_initialized or not self.lightrag_instance:
            return []
        
        try:
            return await self.lightrag_instance.get_graph_labels()
        except Exception as e:
            logger.error(f"그래프 라벨 조회 실패: {str(e)}")
            return []
    
    async def get_knowledge_graph(self, node_label: str, max_depth: int = 3, max_nodes: int = 100) -> Optional[Dict[str, Any]]:
        """지식 그래프 조회"""
        if not self.is_initialized or not self.lightrag_instance:
            return None
        
        try:
            kg = await self.lightrag_instance.get_knowledge_graph(
                node_label=node_label,
                max_depth=max_depth,
                max_nodes=max_nodes
            )
            
            # 응답용 데이터 변환
            nodes_data = []
            if kg.nodes:
                for node in kg.nodes:
                    nodes_data.append({
                        "id": node.id,
                        "properties": node.properties
                    })
            
            edges_data = []
            if kg.edges:
                for edge in kg.edges:
                    edges_data.append({
                        "source": edge.source,
                        "target": edge.target,
                        "properties": edge.properties
                    })
            
            return {
                "nodes": nodes_data,
                "edges": edges_data,
                "node_count": len(nodes_data),
                "edge_count": len(edges_data),
                "is_truncated": getattr(kg, 'is_truncated', False)
            }
        except Exception as e:
            logger.error(f"지식 그래프 조회 실패: {str(e)}")
            return None
    
    async def query_knowledge(self, query: str, mode: str = "hybrid") -> Optional[str]:
        """지식 그래프 질의"""
        if not self.is_initialized or not self.lightrag_instance:
            return None
        
        try:
            query_param = QueryParam(mode=mode)
            answer = await self.lightrag_instance.aquery(
                query=query,
                param=query_param
            )
            return answer
        except Exception as e:
            logger.error(f"지식 그래프 질의 실패: {str(e)}")
            return None
    
    async def delete_document(self, doc_id: str) -> bool:
        """문서 삭제"""
        if not self.is_initialized or not self.lightrag_instance:
            return False
        
        try:
            await self.lightrag_instance.adelete_by_doc_id(doc_id)
            logger.info(f"문서 삭제 완료: {doc_id}")
            return True
        except Exception as e:
            logger.error(f"문서 삭제 실패: {doc_id} - {str(e)}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """서비스 통계 정보"""
        return {
            "workspace": self.workspace,
            "is_initialized": self.is_initialized,
            "chunk_token_size": self.chunk_token_size,
            "chunk_overlap_token_size": self.chunk_overlap_token_size,
            "storage_config": {
                "kv_storage": getattr(self.lightrag_instance, 'kv_storage', None),
                "vector_storage": getattr(self.lightrag_instance, 'vector_storage', None),
                "graph_storage": getattr(self.lightrag_instance, 'graph_storage', None)
            } if self.lightrag_instance else None
        }


# 전역 인스턴스 (싱글톤 패턴)
_graph_service_instance: Optional[GraphService] = None


async def get_graph_service(workspace: str = "default") -> GraphService:
    """
    그래프 서비스 인스턴스 가져오기 (싱글톤)
    
    Args:
        workspace: 워크스페이스 이름
    
    Returns:
        GraphService 인스턴스
    """
    global _graph_service_instance
    
    if _graph_service_instance is None or _graph_service_instance.workspace != workspace:
        _graph_service_instance = GraphService(workspace=workspace)
        await _graph_service_instance.initialize()
    
    return _graph_service_instance


async def cleanup_graph_service():
    """그래프 서비스 정리"""
    global _graph_service_instance
    
    if _graph_service_instance:
        await _graph_service_instance.finalize()
        _graph_service_instance = None