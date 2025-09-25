# 문제 해결 및 FAQ

<cite>
**이 문서에서 참조한 파일**
- [config.py](file://aperag/config.py)
- [exception_handlers.py](file://aperag/exception_handlers.py)
- [document_index.py](file://aperag/db/repositories/document_index.py)
- [manager.py](file://aperag/index/manager.py)
- [vector_index.py](file://aperag/index/vector_index.py)
- [fulltext_index.py](file://aperag/index/fulltext_index.py)
- [litellm_track.py](file://aperag/llm/litellm_track.py)
- [start-api.sh](file://scripts/start-api.sh)
</cite>

## 목차
1. [소개](#소개)
2. [설치 오류](#설치-오류)
3. [인덱싱 실패](#인덱싱-실패)
4. [LLM 호출 시간 초과](#llm-호출-시간-초과)
5. [API 인증 오류](#api-인증-오류)
6. [성능 저하 튜닝 가이드](#성능-저하-튜닝-가이드)
7. [모니터링 지표(Metrics)](#모니터링-지표metrics)

## 소개
ApeRAG은 RAG(Retrieval-Augmented Generation) 기반의 문서 기반 질의응답 시스템으로, 벡터 검색, 풀텍스트 검색, 그래프 검색 등 다양한 인덱싱 방식을 지원합니다. 본 문서는 ApeRAG 사용 중 발생할 수 있는 일반적인 문제와 그 해결 방법을 FAQ 형식으로 정리하며, 설치 오류, 인덱싱 실패, LLM 호출 시간 초과, API 인증 오류 등의 사례를 포함합니다.

**Section sources**
- [config.py](file://aperag/config.py#L1-L332)
- [exception_handlers.py](file://aperag/exception_handlers.py#L1-L114)

## 설치 오류
### 의존성 충돌
#### 증상
`pip install` 또는 `docker-compose up` 실행 시 패키지 버전 충돌로 인해 설치가 실패합니다.

#### 원인 진단 방법
`requirements.txt` 또는 `pyproject.toml`에 명시된 패키지 버전과 현재 환경의 패키지 버전이 충돌하는 경우입니다.

#### 해결 단계
1. 가상 환경을 생성하여 격리된 환경에서 설치를 수행합니다.
   ```bash
   python -m venv aperag-env
   source aperag-env/bin/activate  # Linux/Mac
   aperag-env\Scripts\activate     # Windows
   ```
2. 의존성 파일을 기준으로 패키지를 재설치합니다.
   ```bash
   pip install -r requirements.txt
   ```

### 포트 점유
#### 증상
`start-api.sh` 스크립트 실행 시 `Address already in use` 오류가 발생합니다.

#### 원인 진단 방법
기본 포트(예: 8000, 9200, 6379)를 이미 다른 프로세스가 사용 중입니다.

#### 해결 단계
1. 사용 중인 포트를 확인합니다.
   ```bash
   netstat -tuln | grep :8000
   ```
2. 해당 포트를 사용 중인 프로세스를 종료하거나 `.env` 파일에서 포트를 변경합니다.
   ```env
   POSTGRES_PORT=5433
   REDIS_PORT=6380
   ES_PORT=9201
   ```
3. 스크립트를 다시 실행합니다.
   ```bash
   ./scripts/start-api.sh
   ```

**Section sources**
- [start-api.sh](file://scripts/start-api.sh#L1-L10)
- [config.py](file://aperag/config.py#L100-L110)

## 인덱싱 실패
### 벡터 인덱싱 실패
#### 증상
문서 업로드 후 벡터 인덱싱이 실패하고, 검색 결과가 나오지 않습니다.

#### 원인 진단 방법
1. 로그 파일에서 `Vector index creation failed` 메시지를 확인합니다.
2. Qdrant 서버가 정상적으로 실행 중인지 확인합니다.
3. `model_configs.json` 파일에 임베딩 모델 설정이 올바른지 확인합니다.

#### 해결 단계
1. Qdrant 컨테이너 상태를 확인합니다.
   ```bash
   docker ps | grep qdrant
   ```
2. `config.py`에서 `vector_db_context` 설정을 확인합니다.
   ```python
   vector_db_context: str = Field(
       '{"url":"http://localhost", "port":6333, "distance":"Cosine"}', alias="VECTOR_DB_CONTEXT"
   )
   ```
3. 임베딩 서비스 설정을 확인하고, 필요 시 API 키를 갱신합니다.

**Section sources**
- [vector_index.py](file://aperag/index/vector_index.py#L1-L242)
- [config.py](file://aperag/config.py#L180-L190)

### 풀텍스트 인덱싱 실패
#### 증상
검색어로 문서를 찾을 수 없으며, Elasticsearch에 인덱스가 생성되지 않습니다.

#### 원인 진단 방법
1. `fulltext_index.py`에서 `create_index` 함수의 예외 로그를 확인합니다.
2. Elasticsearch 서버 접근 가능 여부를 확인합니다.
3. `es_host`, `es_port` 설정이 올바른지 확인합니다.

#### 해결 단계
1. Elasticsearch 서버 상태를 확인합니다.
   ```bash
   curl http://localhost:9200
   ```
2. `.env` 파일에서 Elasticsearch 설정을 수정합니다.
   ```env
   ES_HOST_NAME=localhost
   ES_PORT=9200
   ES_USER=
   ES_PASSWORD=
   ```
3. 인덱스를 수동으로 생성합니다.
   ```python
   from aperag.index.fulltext_index import create_index
   create_index("collection_fulltext_index")
   ```

**Section sources**
- [fulltext_index.py](file://aperag/index/fulltext_index.py#L1-L577)
- [config.py](file://aperag/config.py#L120-L130)

## LLM 호출 시간 초과
### 증상
LLM 응답이 지연되거나 타임아웃되어 `504 Gateway Timeout` 오류가 발생합니다.

### 원인 진단 방법
1. `litellm_track.py`에서 `log_failure_event` 로그를 확인합니다.
2. 외부 LLM 제공자(API)의 응답 시간을 확인합니다.
3. 네트워크 지연 또는 대역폭 부족 여부를 점검합니다.

### 해결 단계
1. `config.py`에서 LLM 관련 타임아웃 값을 조정합니다.
   ```python
   # 예: completion_service 타임아웃 연장
   ```
2. `litellm_track.py`에서 로깅 레벨을 DEBUG로 설정하여 상세 로그를 수집합니다.
   ```python
   logger.setLevel(logging.DEBUG)
   ```
3. 외부 LLM 제공자의 상태 페이지를 확인하고, 일시적 장애일 경우 잠시 후 재시도합니다.

**Section sources**
- [litellm_track.py](file://aperag/llm/litellm_track.py#L1-L89)
- [config.py](file://aperag/config.py#L200-L210)

## API 인증 오류
### 증상
API 요청 시 `401 Unauthorized` 또는 `Invalid API key` 오류가 발생합니다.

### 원인 진단 방법
1. 전달된 API 키가 유효한지 확인합니다.
2. `ApiKey` 테이블에서 해당 키의 상태(`status`)가 `ACTIVE`인지 확인합니다.
3. `.env` 파일의 `AUTH_TYPE` 설정을 확인합니다.

### 해결 단계
1. 새로운 API 키를 생성합니다.
   ```python
   from aperag.db.models import ApiKey
   new_key = ApiKey.generate_key()
   ```
2. 데이터베이스에서 API 키 상태를 수동으로 활성화합니다.
   ```sql
   UPDATE api_key SET status = 'ACTIVE' WHERE key = 'sk-xxx';
   ```
3. `auth_type` 설정이 `none`이 아닌 경우, OAuth 클라이언트 정보를 확인합니다.

**Section sources**
- [exception_handlers.py](file://aperag/exception_handlers.py#L1-L114)
- [config.py](file://aperag/config.py#L140-L150)

## 성능 저하 튜닝 가이드
### 데이터베이스 인덱스 최적화
#### 문제
쿼리 속도가 느려지고, `SELECT` 문이 지연됩니다.

#### 해결 방법
1. 자주 조회되는 컬럼에 인덱스를 추가합니다.
   ```sql
   CREATE INDEX idx_document_status ON document(status);
   CREATE INDEX idx_collection_user ON collection(user);
   ```
2. `config.py`에서 DB 풀 설정을 조정합니다.
   ```python
   db_pool_size: int = Field(50, alias="DB_POOL_SIZE")
   db_max_overflow: int = Field(100, alias="DB_MAX_OVERFLOW")
   ```

### 캐시 설정 조정
#### 문제
반복적인 LLM 호출로 인해 비용이 증가하고 응답 속도가 느려집니다.

#### 해결 방법
1. 캐시를 활성화하고 TTL을 적절히 설정합니다.
   ```python
   cache_enabled: bool = Field(True, alias="CACHE_ENABLED")
   cache_ttl: int = Field(3600, alias="CACHE_TTL")  # 1시간
   ```
2. `litellm_cache.py`에서 캐시 백엔드(Redis) 연결을 확인합니다.

**Section sources**
- [config.py](file://aperag/config.py#L190-L200)
- [db/models.py](file://aperag/db/models.py#L1-L1122)

## 모니터링 지표(Metrics)
다음은 ApeRAG 시스템 상태를 모니터링하기 위한 핵심 지표입니다.

| 지표 이름 | 설명 | 경고 임계값 |
|---------|------|-----------|
| `database_connections` | 데이터베이스 연결 수 | 80% 이상 |
| `redis_memory_usage` | Redis 메모리 사용량 | 90% 이상 |
| `qdrant_index_size` | Qdrant 인덱스 크기 | 급격한 증가 |
| `es_query_latency` | Elasticsearch 쿼리 지연 시간 | 평균 500ms 초과 |
| `llm_call_duration` | LLM 호출 지연 시간 | 30초 초과 |
| `failed_index_count` | 실패한 인덱스 건수 | 5건 이상 |
| `api_error_rate` | API 오류 비율 | 5% 이상 |

**Section sources**
- [config.py](file://aperag/config.py#L210-L220)
- [db/models.py](file://aperag/db/models.py#L1-L1122)