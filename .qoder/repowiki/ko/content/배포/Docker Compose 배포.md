# Docker Compose 배포

<cite>
**이 문서에서 참조한 파일**
- [docker-compose.yml](file://docker-compose.yml)
- [scripts/init-es.sh](file://scripts/init-es.sh)
- [scripts/start-api.sh](file://scripts/start-api.sh)
- [scripts/start-celery-worker.sh](file://scripts/start-celery-worker.sh)
- [envs/docker.env.overrides](file://envs/docker.env.overrides)
- [config/celery.py](file://config/celery.py)
- [config/celery_tasks.py](file://config/celery_tasks.py)
</cite>

## 목차
1. [소개](#소개)
2. [프로젝트 구조](#프로젝트-구조)
3. [Docker Compose 구성 분석](#docker-compose-구성-분석)
4. [주요 서비스 역할](#주요-서비스-역할)
5. [환경 변수 설정](#환경-변수-설정)
6. [컨테이너 빌드 및 실행](#컨테이너-빌드-및-실행)
7. [로그 확인 및 오류 진단](#로그-확인-및-오류-진단)
8. [Elasticsearch 초기화 스크립트](#elasticsearch-초기화-스크립트)
9. [Celery 워커 및 비트 관리](#celery-워커-및-비트-관리)
10. [개발 및 프로덕션 환경 비교](#개발-및-프로덕션-환경-비교)
11. [리소스 제한 설정](#리소스-제한-설정)

## 소개
ApeRAG은 RAG(Retrieval-Augmented Generation) 기반의 에이전트 시스템으로, Docker Compose를 사용하여 단일 서버에 통합 배포할 수 있습니다. 이 문서는 docker-compose.yml 파일을 기반으로 각 서비스의 역할, 환경 변수 설정, 컨테이너 실행 방법, 로그 확인 및 오류 진단 절차를 단계별로 설명합니다. 또한 Elasticsearch 초기화 스크립트와 Celery 태스크 관리 방법을 포함하며, 개발 및 프로덕션 환경 간 차이점과 리소스 제한 설정 예시도 제공합니다.

## 프로젝트 구조
ApeRAG 프로젝트는 다음과 같은 주요 디렉터리로 구성되어 있습니다:
- `aperag/`: 핵심 애플리케이션 코드 (API, DB, LLM 등)
- `web/`: 프론트엔드 애플리케이션
- `scripts/`: 시작 및 초기화 스크립트
- `config/`: 구성 파일 (Celery 등)
- `deploy/`: 배포 관련 설정
- 루트 디렉터리: Dockerfile, docker-compose.yml, .env 등 핵심 배포 파일

**Section sources**
- [docker-compose.yml](file://docker-compose.yml#L1-L265)

## Docker Compose 구성 분석
docker-compose.yml 파일은 볼륨 정의, 서비스 그룹화, 의존성 관리, 건강 상태 체크 등을 통해 ApeRAG의 모든 컴포넌트를 통합적으로 관리합니다.

```mermaid
graph TD
subgraph "애플리케이션 서비스"
API[api]
Frontend[frontend]
CeleryWorker[celeryworker]
CeleryBeat[celerybeat]
Flower[flower]
end
subgraph "인프라 서비스"
Postgres[postgres]
Redis[redis]
Qdrant[qdrant]
ES[es]
Jaeger[jaeger]
end
subgraph "선택적 서비스"
Neo4j[neo4j]
DocRay[docray]
DocRayGPU[docray-gpu]
end
API --> Postgres
API --> Redis
API --> Qdrant
API --> ES
Frontend --> API
CeleryWorker --> Postgres
CeleryWorker --> Redis
CeleryWorker --> Qdrant
CeleryWorker --> ES
CeleryBeat --> Postgres
CeleryBeat --> Redis
Flower --> Postgres
Flower --> Redis
```

**Diagram sources**
- [docker-compose.yml](file://docker-compose.yml#L1-L265)

**Section sources**
- [docker-compose.yml](file://docker-compose.yml#L1-L265)

## 주요 서비스 역할
각 서비스는 ApeRAG 아키텍처에서 특정한 역할을 수행합니다.

### API 서비스
백엔드 API 서버로, Alembic을 통한 데이터베이스 마이그레이션 후 Uvicorn으로 실행됩니다. 포트 8000에서 HTTP 요청을 처리하며, 여러 인프라 서비스에 의존합니다.

**Section sources**
- [docker-compose.yml](file://docker-compose.yml#L15-L46)
- [scripts/start-api.sh](file://scripts/start-api.sh#L1-L10)

### Celery 워커 서비스
비동기 백그라운드 태스크를 처리하는 서비스입니다. 문서 인덱싱, 컬렉션 정리 등의 작업을 수행하며, 로컬 큐 이름을 기반으로 태스크를 분배합니다.

**Section sources**
- [docker-compose.yml](file://docker-compose.yml#L77-L104)
- [scripts/start-celery-worker.sh](file://scripts/start-celery-worker.sh#L1-L12)

### Celery 비트 서비스
주기적인 태스크를 스케줄링하는 서비스입니다. 인덱스 조정, 컬렉션 요약 생성, 만료된 문서 정리 등의 주기적 작업을 담당합니다.

**Section sources**
- [docker-compose.yml](file://docker-compose.yml#L106-L128)
- [config/celery.py](file://config/celery.py#L1-L136)

### Redis 서비스
캐싱 및 메시지 브로커로 사용되며, Celery의 작업 큐와 결과 백엔드로 활용됩니다. 건강 상태 체크를 통해 안정적인 연결을 보장합니다.

**Section sources**
- [docker-compose.yml](file://docker-compose.yml#L175-L187)

### PostgreSQL 서비스
주 데이터 저장소로, pgvector 확장을 포함하여 벡터 검색 기능을 지원합니다. Alembic을 통해 스키마 마이그레이션이 관리됩니다.

**Section sources**
- [docker-compose.yml](file://docker-compose.yml#L155-L173)

### Qdrant 서비스
벡터 데이터베이스로, 고성능 벡터 검색을 위해 사용됩니다. 문서의 의미 기반 검색을 가능하게 합니다.

**Section sources**
- [docker-compose.yml](file://docker-compose.yml#L189-L201)

### Elasticsearch 서비스
전문 검색(Full-text Search)을 위한 엔진으로, IK 분석기를 설치하여 한글 검색을 지원합니다. 초기화 스크립트를 통해 자동으로 설정됩니다.

**Section sources**
- [docker-compose.yml](file://docker-compose.yml#L203-L227)
- [scripts/init-es.sh](file://scripts/init-es.sh#L1-L39)

## 환경 변수 설정
`.env` 파일과 `envs/docker.env.overrides` 파일을 통해 다양한 환경 변수를 설정할 수 있습니다.

| 환경 변수 | 설명 | 기본값 |
|---------|------|-------|
| POSTGRES_HOST | PostgreSQL 호스트 | aperag-postgres |
| REDIS_HOST | Redis 호스트 | aperag-redis |
| ES_HOST_NAME | Elasticsearch 호스트 | aperag-es |
| CELERY_BROKER_URL | Celery 브로커 URL | redis://default:password@aperag-redis:6379/0 |
| DATABASE_URL | 데이터베이스 연결 URL | postgresql://postgres:postgres@aperag-postgres:5432/postgres |
| VECTOR_DB_CONTEXT | 벡터 DB 연결 정보 | {"url":"http://aperag-qdrant", "port":6333} |
| ES_HOST | Elasticsearch 호스트 | http://aperag-es:9200 |
| JAEGER_ENABLED | Jaeger 트레이싱 활성화 여부 | True |

**Section sources**
- [envs/docker.env.overrides](file://envs/docker.env.overrides#L1-L29)

## 컨테이너 빌드 및 실행
다음 명령어를 사용하여 ApeRAG을 배포할 수 있습니다:

```bash
# 모든 서비스 빌드 및 실행
docker-compose up --build

# 특정 서비스만 실행 (예: api 및 frontend)
docker-compose up --build api frontend

# 백그라운드에서 실행
docker-compose up -d

# 특정 프로파일 포함 (예: docray)
docker-compose --profile docray up -d
```

## 로그 확인 및 오류 진단
실행 중인 컨테이너의 로그는 다음 명령어로 확인할 수 있습니다:

```bash
# 특정 서비스 로그 확인
docker-compose logs api
docker-compose logs celeryworker

# 실시간 로그 모니터링
docker-compose logs -f

# 최근 N줄 로그 확인
docker-compose logs --tail=100 api
```

주요 오류 유형 및 해결 방법:
- **데이터베이스 연결 실패**: `POSTGRES_HOST`, `REDIS_HOST` 등 네트워크 설정 확인
- **건강 상태 체크 실패**: 종속 서비스가 정상적으로 시작되었는지 확인
- **태스크 실패**: Celery 워커 로그에서 상세 오류 메시지 확인

**Section sources**
- [docker-compose.yml](file://docker-compose.yml#L1-L265)

## Elasticsearch 초기화 스크립트
`scripts/init-es.sh` 스크립트는 Elasticsearch 컨테이너 시작 시 자동으로 실행되어 IK 분석기를 설치하고, 클러스터 상태를 확인합니다.

```mermaid
flowchart TD
Start([스크립트 시작]) --> CheckCommand{"명령어: check?"}
CheckCommand --> |Yes| CheckReady["check_ready() 호출"]
CheckCommand --> |No| InstallIK["IK 분석기 설치 여부 확인"]
InstallIK --> IKInstalled{"설치됨?"}
IKInstalled --> |No| Install["IK 분석기 설치"]
IKInstalled --> |Yes| LogInstalled["설치 완료 로그 출력"]
Install --> LogInstalled
LogInstalled --> StartES["Elasticsearch 시작"]
StartES --> End([스크립트 종료])
```

**Diagram sources**
- [scripts/init-es.sh](file://scripts/init-es.sh#L1-L39)

**Section sources**
- [scripts/init-es.sh](file://scripts/init-es.sh#L1-L39)
- [docker-compose.yml](file://docker-compose.yml#L203-L227)

## Celery 워커 및 비트 관리
Celery 워커와 비트는 독립적으로 관리할 수 있으며, 각각의 시작 스크립트를 통해 실행됩니다.

### Celery 워커 관리
```bash
# 워커 직접 실행 (디버깅 용도)
docker-compose run celeryworker bash
# 내부에서 직접 스크립트 실행
/app/scripts/start-celery-worker.sh
```

### Celery 비트 관리
```bash
# 비트 직접 실행
docker-compose run celerybeat bash
/app/scripts/start-celery-beat.sh
```

### Flower를 통한 모니터링
Flower는 Celery 태스크를 웹 기반으로 모니터링할 수 있는 도구로, 포트 5555에서 접근 가능합니다.

**Section sources**
- [scripts/start-celery-worker.sh](file://scripts/start-celery-worker.sh#L1-L12)
- [config/celery.py](file://config/celery.py#L1-L136)
- [config/celery_tasks.py](file://config/celery_tasks.py#L1-L942)

## 개발 및 프로덕션 환경 비교
| 항목 | 개발 환경 | 프로덕션 환경 |
|------|----------|-------------|
| 이미지 태그 | nightly | 안정된 버전 |
| 리소스 제한 | 없음 | CPU/Memory 제한 설정 |
| Jaeger | 기본 포함 | 선택적 활성화 |
| DocRay | CPU/GPU 선택 가능 | GPU 우선 |
| 로깅 수준 | DEBUG | INFO/WARNING |
| 재시작 정책 | on-failure | unless-stopped |

**Section sources**
- [docker-compose.yml](file://docker-compose.yml#L1-L265)

## 리소스 제한 설정
Docker Compose를 통해 CPU 및 메모리 제한을 설정할 수 있습니다.

```yaml
services:
  docray-gpu:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
          memory: 8G
```

또는 일반 서비스에 대해 다음과 같이 설정할 수 있습니다:

```yaml
services:
  api:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '0.5'
          memory: 512M
```

이러한 설정은 리소스 경쟁을 방지하고, 시스템 안정성을 향상시킵니다.

**Section sources**
- [docker-compose.yml](file://docker-compose.yml#L255-L264)