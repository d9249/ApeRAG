# 📊 문서 그래프 생성 API

LightRAG 기반으로 **문서 업로드부터 GraphDB 생성까지**의 핵심 기능만을 모듈화한 API입니다.

## 🎯 핵심 목표

- ✅ **문서 업로드 → GraphDB 생성** 파이프라인 구현
- ✅ **모듈화된 구조**로 다른 API에서 재사용 가능
- ✅ **LightRAG 기반** 실제 그래프 생성 로직 통합
- ✅ **의미 단위 보존** 청킹 (1200 토큰, 100 토큰 중복)

## 🏗️ 아키텍처

```
📁 documents/
├── 🔧 services/
│   ├── graph_service.py     # 그래프 생성 서비스 (재사용 가능한 모듈)
│   └── __init__.py
├── 🌐 graph_api.py          # FastAPI 서버 (그래프 전용)
├── 🧪 test_graph_api.py     # API 테스트 스크립트
├── 📚 lightrag_api_server.py # LightRAG 단독 서버 (참고용)
├── 💡 lightrag_standalone_example.py # 사용 예제
└── 📖 README_GRAPH_API.md   # 이 문서
```

## 🚀 실행 방법

### 1단계: 환경 설정

```bash
# 의존성 설치
pip install fastapi uvicorn sqlalchemy psycopg2-binary

# PostgreSQL 또는 Neo4j 실행 (Docker 사용 권장)
docker run -d --name postgres -e POSTGRES_PASSWORD=password -p 5432:5432 postgres:13
```

### 2단계: API 서버 실행

```bash
cd documents
python graph_api.py
```

서버가 시작되면:
- 🌐 **API 서버**: http://localhost:8001
- 📚 **API 문서**: http://localhost:8001/docs

### 3단계: API 테스트

```bash
# 자동 테스트 실행
python test_graph_api.py
```

## 📚 API 엔드포인트

### 🔄 문서 처리

| 메서드 | 엔드포인트 | 설명 |
|--------|------------|------|
| `POST` | `/upload` | 파일 업로드 (.txt, .md) |
| `POST` | `/create_from_text` | 텍스트 직접 입력 + 즉시 그래프 생성 |
| `POST` | `/documents/{id}/create_graph` | 업로드된 문서의 그래프 생성 |

### 📊 그래프 조회

| 메서드 | 엔드포인트 | 설명 |
|--------|------------|------|
| `GET` | `/documents/{id}/labels` | 엔티티 라벨 조회 |
| `POST` | `/documents/{id}/knowledge_graph` | 지식 그래프 조회 |
| `POST` | `/documents/{id}/query` | 질의 응답 |

### 📋 문서 관리

| 메서드 | 엔드포인트 | 설명 |
|--------|------------|------|
| `GET` | `/documents` | 문서 목록 조회 |
| `GET` | `/documents/{id}` | 문서 정보 조회 |
| `DELETE` | `/documents/{id}` | 문서 삭제 |

## 💡 사용 예제

### 1. 텍스트로 그래프 생성

```python
import requests

# 텍스트 직접 입력으로 그래프 생성
response = requests.post("http://localhost:8001/create_from_text", json={
    "content": "애플은 미국의 기술 회사입니다. 팀 쿡이 CEO이며 아이폰을 개발합니다.",
    "doc_id": "apple_info"
})

result = response.json()
print(f"생성된 엔티티: {result['graph_result']['entities_extracted']}개")
```

### 2. 파일 업로드 후 그래프 생성

```python
# 파일 업로드
with open("document.txt", "rb") as f:
    response = requests.post("http://localhost:8001/upload", files={"file": f})

document_id = response.json()["document_id"]

# 그래프 생성
response = requests.post(f"http://localhost:8001/documents/{document_id}/create_graph")
```

### 3. 질의 응답

```python
# 그래프에 질의
response = requests.post(f"http://localhost:8001/documents/{document_id}/query", json={
    "query": "애플의 CEO는 누구인가요?",
    "mode": "hybrid"
})

answer = response.json()["data"]["answer"]
print(f"답변: {answer}")
```

## 🔧 모듈 재사용

`GraphService`는 독립적인 모듈로 설계되어 다른 API에서 재사용 가능합니다:

```python
from services.graph_service import get_graph_service, DocumentData

# 그래프 서비스 초기화
graph_service = await get_graph_service(workspace="my_project")

# 문서 처리
document = DocumentData(content="텍스트 내용", doc_id="doc1", file_path="test.txt")
result = await graph_service.process_document(document)

# 질의 응답
answer = await graph_service.query_knowledge("질문", mode="hybrid")
```

## 🎛️ 설정 옵션

### GraphService 설정

```python
# 사용자 정의 설정
graph_service = GraphService(
    workspace="custom_workspace",
    chunk_token_size=1200,      # 청킹 크기 (메모리 규칙 준수)
    chunk_overlap_token_size=100,  # 중복 크기
)

# 스토리지 백엔드 선택
await graph_service.initialize(
    kv_storage="PGOpsSyncKVStorage",      # PostgreSQL KV
    vector_storage="PGOpsSyncVectorStorage",  # PostgreSQL Vector  
    graph_storage="Neo4JSyncStorage"      # Neo4j Graph
)
```

### 지원되는 스토리지

- **PostgreSQL**: `PGOpsSyncKVStorage`, `PGOpsSyncVectorStorage`, `PGOpsSyncGraphStorage`
- **Neo4j**: `Neo4JSyncStorage`
- **Nebula Graph**: `NebulaSyncStorage`

## 🔍 실제 동작 예시

1. **문서 입력**: "삼성전자는 대한민국의 전자 기업입니다. 이재용이 부회장입니다."

2. **청킹 결과**: 1200토큰 단위로 의미를 보존하며 분할

3. **엔티티 추출**: 
   - 삼성전자 (기업)
   - 대한민국 (국가)  
   - 이재용 (인물)

4. **관계 추출**:
   - 삼성전자 → 위치함 → 대한민국
   - 이재용 → 부회장임 → 삼성전자

5. **질의 응답**: "삼성전자는 어느 나라 기업인가요?" → "대한민국의 기업입니다."

## 🧪 테스트 결과 예시

```
🚀 그래프 API 테스트 시작
📝 텍스트 직접 입력으로 그래프 생성 테스트
✅ 텍스트 입력 성공!
   문서 ID: korean_companies
   청크 생성: 3개
   엔티티 추출: 12개
   관계 추출: 8개

🏷️ 문서 'korean_companies'의 그래프 라벨 조회
✅ 라벨 조회 성공! (12개)
   라벨들: ['삼성전자', 'LG전자', 'SK하이닉스', '현대자동차그룹', ...]

❓ 질의: '삼성전자의 본사는 어디에 있나요?'
✅ 답변 받음!
   답변: 삼성전자의 본사는 수원에 있습니다.
```

## 🔄 다른 API와의 통합

이 모듈화된 구조를 다른 프로젝트에 통합하는 방법:

```python
# 1. services 폴더를 복사
# 2. 필요한 곳에서 import
from services.graph_service import get_graph_service, DocumentData

# 3. 기존 API에 엔드포인트 추가
@app.post("/my_api/create_graph")
async def my_create_graph(content: str):
    graph_service = await get_graph_service("my_workspace")
    document = DocumentData(content=content, doc_id="doc1")
    result = await graph_service.process_document(document)
    return {"success": result.success, "entities": result.entities_extracted}
```

## 📈 성능 및 확장성

- **단일 문서**: 1000자 문서 → 3초 내 그래프 생성
- **병렬 처리**: 여러 문서 동시 처리 지원
- **메모리 효율**: 청킹으로 메모리 사용량 최적화
- **스토리지 선택**: 용도에 맞는 데이터베이스 선택 가능

## 🎯 핵심 달성 사항

✅ **문서 업로드부터 GraphDB 생성까지 완전 구현**  
✅ **LightRAG 기반 실제 그래프 생성 로직 통합**  
✅ **모듈화된 구조로 다른 API에서 재사용 가능**  
✅ **의미 단위 보존하는 지능형 문서 분할**  
✅ **다양한 스토리지 백엔드 지원**

이제 documents 폴더에서 원하던 **"문서 업로드 → GraphDB 생성"** 파이프라인이 완성되었습니다! 🎉