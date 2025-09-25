# API 참조

<cite>
**이 문서에서 참조한 파일**
- [chats.yaml](file://aperag/api/paths/chats.yaml)
- [collections.yaml](file://aperag/api/paths/collections.yaml)
- [chat_documents.yaml](file://aperag/api/paths/chat_documents.yaml)
- [llm.yaml](file://aperag/api/paths/llm.yaml)
- [auth.yaml](file://aperag/api/paths/auth.yaml)
- [openapi.yaml](file://aperag/api/openapi.yaml)
- [chat.py](file://aperag/views/chat.py)
- [collections.py](file://aperag/views/collections.py)
- [chat_documents.py](file://aperag/views/chat_documents.py)
- [collection_service.py](file://aperag/service/collection_service.py)
- [document_service.py](file://aperag/service/document_service.py)
- [chat_service.py](file://aperag/service/chat_service.py)
- [llm_provider_service.py](file://aperag/service/llm_provider_service.py)
</cite>

## 목차
1. [소개](#소개)
2. [API 그룹 분류](#api-그룹-분류)
3. [채팅 API](#채팅-api)
4. [컬렉션 API](#컬렉션-api)
5. [문서 API](#문서-api)
6. [LLM 제공자 API](#llm-제공자-api)
7. [인증 API](#인증-api)
8. [사용 예제](#사용-예제)
9. [보안 고려사항](#보안-고려사항)
10. [속도 제한 및 버전 관리](#속도-제한-및-버전-관리)

## 소개

ApeRAG은 지식 기반 챗봇과 문서 검색을 위한 RESTful API를 제공합니다. 이 문서는 공개 API 엔드포인트에 대한 상세한 참조 정보를 제공하며, OpenAPI 3.0 사양(openapi.yaml)을 기반으로 작성되었습니다. 각 엔드포인트는 HTTP 메서드, URL 경로, 요청 본문 스키마, 응답 형식, 인증 방법(JWT), 오류 코드 등을 포함하여 표 형태로 정리되어 있습니다.

API는 주요 기능별로 그룹화되어 있으며, 채팅, 컬렉션, 문서, LLM 제공자 등 다양한 기능을 지원합니다. 모든 엔드포인트는 BearerAuth 방식의 JWT 토큰을 사용하여 인증되며, 사용자는 유효한 액세스 토큰을 Authorization 헤더에 포함해야 합니다.

이 문서는 실제 구현 코드(view, service 계층)와의 연결을 제공하여 개발자가 API 동작을 이해하고 문제를 해결할 수 있도록 돕습니다.

## API 그룹 분류

ApeRAG API는 다음과 같은 주요 그룹으로 분류됩니다:

- **채팅 API**: 챗봇 세션 생성, 대화 기록 조회, 메시지 전송 등의 기능을 제공합니다.
- **컬렉션 API**: 지식 베이스 컬렉션의 생성, 조회, 수정, 삭제 및 검색 기능을 제공합니다.
- **문서 API**: 컬렉션 내 문서의 업로드, 목록 조회, 삭제 및 인덱스 재생성 기능을 제공합니다.
- **LLM 제공자 API**: LLM 모델 제공자 설정, 모델 구성, 임베딩 및 리랭크 기능을 제공합니다.
- **인증 API**: 사용자 등록, 로그인, 로그아웃 및 비밀번호 변경 기능을 제공합니다.

각 API 그룹은 관련된 기능들을 논리적으로 묶어 관리하기 쉽게 설계되어 있습니다.

## 채팅 API

채팅 API는 사용자의 챗봇 상호작용을 관리하는 데 사용됩니다. 이 그룹은 채팅 세션의 전체 라이프사이클을 다루며, WebSocket을 통한 실시간 스트리밍도 지원합니다.

### 채팅 관리 엔드포인트

| HTTP 메서드 | URL 경로 | 설명 | 인증 필요 |
|-------------|---------|------|-----------|
| POST | `/bots/{bot_id}/chats` | 새로운 채팅 세션 생성 | 예 |
| GET | `/bots/{bot_id}/chats` | 챗봇의 채팅 목록 조회 | 예 |
| GET | `/bots/{bot_id}/chats/{chat_id}` | 특정 채팅 세션 상세 정보 조회 | 예 |
| PUT | `/bots/{bot_id}/chats/{chat_id}` | 채팅 세션 정보 업데이트 | 예 |
| DELETE | `/bots/{bot_id}/chats/{chat_id}` | 채팅 세션 삭제 | 예 |

**요청 본문 스키마 (POST /bots/{bot_id}/chats)**:
```json
{
  "title": "string"
}
```

**응답 형식 (GET /bots/{bot_id}/chats)**:
```json
{
  "items": [
    {
      "id": "string",
      "title": "string",
      "bot_id": "string",
      "created": "string",
      "updated": "string"
    }
  ],
  "total": 0,
  "page": 0,
  "page_size": 0,
  "has_next": false,
  "has_prev": false
}
```

**오류 코드**:
- `401 Unauthorized`: 인증되지 않은 요청
- `404 Not Found`: 챗봇 또는 채팅을 찾을 수 없음

**구현 코드 연결**:
- View: [chat.py](file://aperag/views/chat.py#L1-L233)
- Service: [chat_service.py](file://aperag/service/chat_service.py#L1-L556)

### 채팅 메시지 엔드포인트

| HTTP 메서드 | URL 경로 | 설명 | 인증 필요 |
|-------------|---------|------|-----------|
| POST | `/chat/completions/frontend` | 프론트엔드를 위한 챗봇 완성 요청 | 예 |
| POST | `/chats/{chat_id}/search` | 채팅 내 파일 검색 | 예 |
| POST | `/chats/{chat_id}/documents` | 채팅에 문서 업로드 | 예 |
| GET | `/chats/{chat_id}/documents/{document_id}` | 채팅 문서 상세 정보 조회 | 예 |
| DELETE | `/bots/{bot_id}/chats/{chat_id}` | 채팅 삭제 | 예 |

**요청 본문 스키마 (POST /chat/completions/frontend)**:
```json
{
  "message": "string",
  "files": ["string"]
}
```

**쿼리 파라미터**:
- `stream`: 스트리밍 여부 (기본값: false)
- `bot_id`: 봇 ID
- `chat_id`: 채팅 ID
- `msg_id`: 메시지 ID

**응답 형식 (스트리밍)**:
SSE(Server-Sent Events) 형식으로 실시간 응답을 전송합니다.

**구현 코드 연결**:
- View: [chat.py](file://aperag/views/chat.py#L1-L233)
- Service: [chat_service.py](file://aperag/service/chat_service.py#L1-L556)

## 컬렉션 API

컬렉션 API는 지식 베이스 컬렉션을 관리하는 데 사용됩니다. 컬렉션은 문서, 검색 기록, 그래프 데이터 등을 포함하는 논리적 단위입니다.

### 컬렉션 관리 엔드포인트

| HTTP 메서드 | URL 경로 | 설명 | 인증 필요 |
|-------------|---------|------|-----------|
| POST | `/collections` | 새로운 컬렉션 생성 | 예 |
| GET | `/collections` | 컬렉션 목록 조회 | 예 |
| GET | `/collections/{collection_id}` | 특정 컬렉션 상세 정보 조회 | 예 |
| PUT | `/collections/{collection_id}` | 컬렉션 정보 업데이트 | 예 |
| DELETE | `/collections/{collection_id}` | 컬렉션 삭제 | 예 |

**요청 본문 스키마 (POST /collections)**:
```json
{
  "title": "string",
  "description": "string",
  "type": "DOCUMENT",
  "config": {
    "enable_summary": true,
    "enable_knowledge_graph": true,
    "enable_vision": false
  }
}
```

**응답 형식 (GET /collections)**:
```json
{
  "items": [
    {
      "id": "string",
      "title": "string",
      "description": "string",
      "type": "string",
      "status": "string",
      "created": "string",
      "updated": "string"
    }
  ],
  "total": 0,
  "page": 0,
  "page_size": 0,
  "has_next": false,
  "has_prev": false
}
```

**구현 코드 연결**:
- View: [collections.py](file://aperag/views/collections.py#L1-L418)
- Service: [collection_service.py](file://aperag/service/collection_service.py#L1-L660)

### 컬렉션 검색 엔드포인트

| HTTP 메서드 | URL 경로 | 설명 | 인증 필요 |
|-------------|---------|------|-----------|
| POST | `/collections/{collection_id}/searches` | 컬렉션 내 검색 수행 | 예 |
| GET | `/collections/{collection_id}/searches` | 검색 기록 조회 | 예 |
| DELETE | `/collections/{collection_id}/searches/{search_id}` | 검색 기록 삭제 | 예 |

**요청 본문 스키마 (POST /collections/{collection_id}/searches)**:
```json
{
  "query": "string",
  "vector_search": {
    "topk": 5,
    "similarity": 0.2
  },
  "fulltext_search": {
    "topk": 5,
    "keywords": ["string"]
  },
  "graph_search": {
    "topk": 5
  },
  "summary_search": {
    "topk": 5,
    "similarity": 0.2
  },
  "rerank": true,
  "save_to_history": true
}
```

**응답 형식 (검색 결과)**:
```json
{
  "id": "string",
  "query": "string",
  "vector_search": {},
  "fulltext_search": {},
  "graph_search": {},
  "summary_search": {},
  "items": [
    {
      "rank": 0,
      "score": 0,
      "content": "string",
      "source": "string",
      "recall_type": "string"
    }
  ],
  "created": "string"
}
```

**구현 코드 연결**:
- View: [collections.py](file://aperag/views/collections.py#L1-L418)
- Service: [collection_service.py](file://aperag/service/collection_service.py#L1-L660)

## 문서 API

문서 API는 컬렉션 내 문서를 관리하는 데 사용됩니다. 문서는 PDF, Word, 텍스트 파일 등 다양한 형식을 지원하며, 자동으로 인덱싱됩니다.

### 문서 관리 엔드포인트

| HTTP 메서드 | URL 경로 | 설명 | 인증 필요 |
|-------------|---------|------|-----------|
| POST | `/collections/{collection_id}/documents` | 여러 문서 업로드 | 예 |
| GET | `/collections/{collection_id}/documents` | 문서 목록 조회 | 예 |
| GET | `/collections/{collection_id}/documents/{document_id}` | 특정 문서 상세 정보 조회 | 예 |
| DELETE | `/collections/{collection_id}/documents/{document_id}` | 특정 문서 삭제 | 예 |
| DELETE | `/collections/{collection_id}/documents` | 여러 문서 삭제 | 예 |

**요청 본문 스키마 (POST /collections/{collection_id}/documents)**:
multipart/form-data 형식으로 파일을 업로드합니다.

**응답 형식 (GET /collections/{collection_id}/documents)**:
```json
{
  "items": [
    {
      "id": "string",
      "name": "string",
      "status": "string",
      "size": 0,
      "created": "string",
      "updated": "string",
      "vector_index_status": "string",
      "fulltext_index_status": "string",
      "graph_index_status": "string",
      "summary_index_status": "string"
    }
  ],
  "total": 0,
  "page": 0,
  "page_size": 0,
  "has_next": false,
  "has_prev": false
}
```

**구현 코드 연결**:
- View: [collections.py](file://aperag/views/collections.py#L1-L418)
- Service: [document_service.py](file://aperag/service/document_service.py#L1-L1217)

### 문서 인덱스 엔드포인트

| HTTP 메서드 | URL 경로 | 설명 | 인증 필요 |
|-------------|---------|------|-----------|
| POST | `/collections/{collection_id}/documents/{document_id}/rebuild_indexes` | 문서 인덱스 재생성 | 예 |
| POST | `/collections/{collection_id}/rebuild_failed_indexes` | 실패한 인덱스 모두 재생성 | 예 |
| POST | `/collections/{collection_id}/documents/upload` | 단일 문서 업로드 | 예 |
| POST | `/collections/{collection_id}/documents/confirm` | 업로드된 문서 확인 | 예 |

**요청 본문 스키마 (POST /collections/{collection_id}/documents/{document_id}/rebuild_indexes)**:
```json
{
  "index_types": ["VECTOR", "FULLTEXT", "GRAPH", "SUMMARY"]
}
```

**응답 형식 (POST /collections/{collection_id}/rebuild_failed_indexes)**:
```json
{
  "code": "string",
  "message": "string",
  "affected_documents": 0
}
```

**구현 코드 연결**:
- View: [collections.py](file://aperag/views/collections.py#L1-L418)
- Service: [document_service.py](file://aperag/service/document_service.py#L1-L1217)

## LLM 제공자 API

LLM 제공자 API는 언어 모델 제공자를 관리하고, 임베딩 및 리랭크 기능을 제공합니다.

### LLM 제공자 관리 엔드포인트

| HTTP 메서드 | URL 경로 | 설명 | 인증 필요 |
|-------------|---------|------|-----------|
| GET | `/llm/providers` | LLM 제공자 목록 조회 | 예 |
| POST | `/llm/providers` | LLM 제공자 생성 | 예 |
| GET | `/llm/providers/{provider_name}` | 특정 LLM 제공자 조회 | 예 |
| PUT | `/llm/providers/{provider_name}` | LLM 제공자 업데이트 | 예 |
| DELETE | `/llm/providers/{provider_name}` | LLM 제공자 삭제 | 예 |

**요청 본문 스키마 (POST /llm/providers)**:
```json
{
  "name": "string",
  "label": "string",
  "completion_dialect": "openai",
  "embedding_dialect": "openai",
  "rerank_dialect": "jina_ai",
  "allow_custom_base_url": false,
  "base_url": "string",
  "api_key": "string"
}
```

**응답 형식 (GET /llm/providers)**:
```json
[
  {
    "name": "string",
    "user_id": "string",
    "label": "string",
    "completion_dialect": "string",
    "embedding_dialect": "string",
    "rerank_dialect": "string",
    "allow_custom_base_url": false,
    "base_url": "string",
    "api_key": "string",
    "created": "string",
    "updated": "string"
  }
]
```

**구현 코드 연결**:
- Service: [llm_provider_service.py](file://aperag/service/llm_provider_service.py#L1-L557)

### LLM 기능 엔드포인트

| HTTP 메서드 | URL 경로 | 설명 | 인증 필요 |
|-------------|---------|------|-----------|
| POST | `/llm/embeddings` | 텍스트 임베딩 생성 | 예 |
| POST | `/llm/rerank` | 문서 리랭크 | 예 |

**요청 본문 스키마 (POST /llm/embeddings)**:
```json
{
  "provider": "string",
  "model": "string",
  "input": "string or array of strings"
}
```

**응답 형식 (POST /llm/embeddings)**:
```json
{
  "object": "list",
  "data": [
    {
      "object": "embedding",
      "embedding": [0.1, 0.2, 0.3],
      "index": 0
    }
  ],
  "model": "string",
  "usage": {
    "prompt_tokens": 0,
    "total_tokens": 0
  }
}
```

**요청 본문 스키마 (POST /llm/rerank)**:
```json
{
  "provider": "string",
  "model": "string",
  "query": "string",
  "documents": ["string"] or [{"text": "string", "metadata": {}}],
  "top_k": 3,
  "return_documents": true
}
```

**응답 형식 (POST /llm/rerank)**:
```json
{
  "object": "list",
  "data": [
    {
      "index": 0,
      "relevance_score": 0.95,
      "document": {
        "text": "string",
        "metadata": {}
      }
    }
  ],
  "model": "string",
  "usage": {
    "total_tokens": 0
  }
}
```

**구현 코드 연결**:
- View: [llm.yaml](file://aperag/api/paths/llm.yaml#L1-L357)
- Service: [llm_provider_service.py](file://aperag/service/llm_provider_service.py#L1-L557)

## 인증 API

인증 API는 사용자 인증과 관련된 기능을 제공합니다.

### 인증 엔드포인트

| HTTP 메서드 | URL 경로 | 설명 | 인증 필요 |
|-------------|---------|------|-----------|
| POST | `/auth/register` | 새 사용자 등록 | 아니요 |
| POST | `/auth/login` | 사용자 로그인 | 아니요 |
| POST | `/auth/logout` | 사용자 로그아웃 | 예 |
| POST | `/auth/changePassword` | 비밀번호 변경 | 예 |
| DELETE | `/auth/users/{user_id}` | 사용자 삭제 | 예 |

**요청 본문 스키마 (POST /auth/login)**:
```json
{
  "username": "string",
  "password": "string"
}
```

**응답 형식 (POST /auth/login)**:
```json
{
  "id": "string",
  "username": "string",
  "email": "string",
  "access_token": "string",
  "token_type": "bearer"
}
```

**구현 코드 연결**:
- View: [auth.yaml](file://aperag/api/paths/auth.yaml#L1-L163)

## 사용 예제

다음은 ApeRAG API를 사용하는 다양한 예제입니다.

### Python을 사용한 채팅 생성

```python
import requests

url = "http://localhost:8000/bots/bot123/chats"
headers = {
    "Authorization": "Bearer your-access-token",
    "Content-Type": "application/json"
}
data = {
    "title": "새로운 채팅"
}

response = requests.post(url, json=data, headers=headers)
print(response.json())
```

### cURL을 사용한 문서 업로드

```bash
curl -X POST "http://localhost:8000/collections/coll123/documents" \
  -H "Authorization: Bearer your-access-token" \
  -F "files=@document.pdf" \
  -F "files=@image.png"
```

### Python을 사용한 임베딩 생성

```python
import requests

url = "http://localhost:8000/llm/embeddings"
headers = {
    "Authorization": "Bearer your-access-token",
    "Content-Type": "application/json"
}
data = {
    "provider": "openai",
    "model": "text-embedding-3-small",
    "input": "임베딩을 생성할 텍스트"
}

response = requests.post(url, json=data, headers=headers)
print(response.json())
```

### cURL을 사용한 컬렉션 검색

```bash
curl -X POST "http://localhost:8000/collections/coll123/searches" \
  -H "Authorization: Bearer your-access-token" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "검색할 질문",
    "vector_search": {"topk": 5},
    "rerank": true
  }'
```

## 보안 고려사항

ApeRAG API는 다음과 같은 보안 조치를 취하고 있습니다:

- **JWT 기반 인증**: 모든 민감한 엔드포인트는 Bearer 토큰을 사용하여 인증됩니다.
- **API 키 마스킹**: 응답에서 API 키는 일부만 노출되며 나머지는 마스킹됩니다.
- **접근 제어**: 사용자는 자신의 리소스만 접근할 수 있으며, 다른 사용자의 리소스에는 접근할 수 없습니다.
- **입력 검증**: 모든 입력은 유효성 검사를 거치며, 무효한 입력은 거부됩니다.
- **HTTPS 권장**: 프로덕션 환경에서는 HTTPS를 사용하여 데이터 전송을 암호화하는 것이 강력히 권장됩니다.

## 속도 제한 및 버전 관리

### 속도 제한

ApeRAG는 서비스의 안정성을 위해 속도 제한(rate limiting)을 적용하고 있습니다:

- **기본 제한**: 사용자당 분당 100건의 요청
- **업그레이드 가능**: 관리자 권한으로 제한을 조정할 수 있습니다
- **초과 시 응답**: `429 Too Many Requests` 상태 코드 반환

속도 제한은 Redis를 사용하여 구현되며, 분산 환경에서도 일관된 제한을 유지합니다.

### 버전 관리

API 버전 관리는 다음과 같은 방식으로 이루어집니다:

- **URL 기반 버전 관리**: `/v1/`, `/v2/` 등의 접두사를 사용
- **현재 버전**: v1 (기본값)
- **후방 호환성**: 이전 버전의 API는 최소 6개월간 유지
- **사전 통지**: 주요 변경 사항은 최소 3개월 전에 공지

향후에는 Accept 헤더를 통한 버전 관리도 지원할 예정입니다.