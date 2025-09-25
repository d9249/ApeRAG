# 컬렉션 API

<cite>
**이 문서에서 참조한 파일**
- [collections.yaml](file://aperag/api/paths/collections.yaml)
- [collection.yaml](file://aperag/api/components/schemas/collection.yaml)
- [document.yaml](file://aperag/api/components/schemas/document.yaml)
- [collection_service.py](file://aperag/service/collection_service.py)
- [document_service.py](file://aperag/service/document_service.py)
- [collections.py](file://aperag/views/collections.py)
</cite>

## 목차
1. [소개](#소개)
2. [핵심 기능 개요](#핵심-기능-개요)
3. [컬렉션 관리 엔드포인트](#컬렉션-관리-엔드포인트)
4. [문서 관리 엔드포인트](#문서-관리-엔드포인트)
5. [검색 및 지식 그래프 엔드포인트](#검색-및-지식-그래프-엔드포인트)
6. [권한 및 인증 요구사항](#권한-및-인증-요구사항)
7. [사용 예제: 컬렉션 생성 및 문서 업로드](#사용-예제-컬렉션-생성-및-문서-업로드)
8. [오류 처리 전략](#오류-처리-전략)
9. [성능 최적화 팁](#성능-최적화-팁)

## 소개

이 문서는 ApeRAG 시스템의 컬렉션 관리를 위한 RESTful API를 철저히 설명합니다. 컬렉션은 관련 문서들을 그룹화하고 관리하는 핵심 단위이며, 이 API는 컬렉션과 그 내부 문서에 대한 생성, 조회, 수정, 삭제, 검색, 공유 설정 등의 포괄적인 기능을 제공합니다. 본 문서는 각 엔드포인트의 HTTP 메서드, 요청/응답 스키마, 중첩된 경로 구조, 그리고 보안 요구사항을 상세히 기술합니다.

**Section sources**
- [collections.yaml](file://aperag/api/paths/collections.yaml#L1-L1304)
- [collection_service.py](file://aperag/service/collection_service.py#L1-L660)

## 핵심 기능 개요

ApeRAG의 컬렉션 API는 다음과 같은 주요 기능을 제공합니다:

*   **CRUD 작업**: 사용자는 `POST`, `GET`, `PUT`, `DELETE` 메서드를 통해 컬렉션과 문서를 완전히 관리할 수 있습니다.
*   **중첩된 자원 구조**: `/collections/{id}/documents`와 같은 중첩된 엔드포인트를 통해 컬렉션과 문서 간의 계층적 관계를 명확하게 표현합니다.
*   **고급 검색**: 벡터 검색, 풀텍스트 검색, 지식 그래프 검색 등 다양한 검색 유형을 지원하며, 결과 재정렬(rerank) 기능도 포함되어 있습니다.
*   **지식 그래프 통합**: 컬렉션 내 문서로부터 추출된 정보를 기반으로 지식 그래프를 생성하고 탐색할 수 있는 전용 엔드포인트를 제공합니다.
*   **공유 및 마켓플레이스**: 컬렉션을 다른 사용자와 공유하거나 마켓플레이스에 게시하여 배포할 수 있는 기능을 지원합니다.
*   **대량 처리 및 배치 작업**: 다수의 문서를 한 번에 업로드하고 확인하는 워크플로우를 통해 대량 데이터 처리를 효율적으로 수행할 수 있습니다.

## 컬렉션 관리 엔드포인트

### 컬렉션 생성 (`POST /collections`)
새로운 컬렉션을 생성합니다. 요청 본문에는 `CollectionCreate` 스키마가 필요합니다.

**요청 본문 (CollectionCreate)**:
```json
{
  "title": "string",
  "description": "string",
  "type": "DOCUMENT", // 현재 지원되는 유일한 타입
  "config": {
    "enable_vector": true,
    "enable_fulltext": true,
    "enable_knowledge_graph": false,
    "enable_summary": false,
    "enable_vision": false,
    "embedding": { /* modelSpec */ },
    "completion": { /* modelSpec */ }
  },
  "source": { /* collectionSource */ }
}
```

**응답 형식 (201 Created)**:
`Collection` 객체를 반환합니다. 주요 속성은 `id`, `title`, `status`, `created`, `updated`입니다.

**Section sources**
- [collections.yaml](file://aperag/api/paths/collections.yaml#L1-L50)
- [collection.yaml](file://aperag/api/components/schemas/collection.yaml#L1-L491)
- [collection_service.py](file://aperag/service/collection_service.py#L50-L100)

### 컬렉션 목록 조회 (`GET /collections`)
사용자가 소유하거나 구독한 모든 컬렉션의 목록을 페이지네이션과 함께 조회합니다.

**쿼리 매개변수**:
- `page`: 페이지 번호 (기본값: 1)
- `page_size`: 페이지당 항목 수 (기본값: 10)
- `include_subscribed`: 구독한 컬렉션을 결과에 포함할지 여부 (기본값: true)

**응답 형식 (200 OK)**:
`collectionViewList` 객체를 반환합니다. 이는 `CollectionView` 객체의 배열과 페이지 정보(`pageResult`)를 포함합니다. `CollectionView`는 `id`, `title`, `owner_username`, `is_published` 등의 경량 정보를 제공합니다.

**Section sources**
- [collections.yaml](file://aperag/api/paths/collections.yaml#L51-L100)
- [collection.yaml](file://aperag/api/components/schemas/collection.yaml#L1-L491)

### 컬렉션 상세 조회 (`GET /collections/{collection_id}`)
특정 컬렉션의 전체 세부 정보를 조회합니다.

**경로 매개변수**:
- `collection_id`: 조회할 컬렉션의 고유 식별자.

**응답 형식 (200 OK)**:
`Collection` 객체를 반환합니다.

**Section sources**
- [collections.yaml](file://aperag/api/paths/collections.yaml#L101-L150)
- [collection_service.py](file://aperag/service/collection_service.py#L200-L220)

### 컬렉션 수정 (`PUT /collections/{collection_id}`)
기존 컬렉션의 제목, 설명 또는 구성(config)을 업데이트합니다.

**요청 본문 (CollectionUpdate)**:
`CollectionCreate`와 동일하지만 `title`과 `description`이 선택 사항입니다.

**응답 형식 (200 OK)**:
업데이트된 `Collection` 객체를 반환합니다.

**Section sources**
- [collections.yaml](file://aperag/api/paths/collections.yaml#L151-L200)
- [collection_service.py](file://aperag/service/collection_service.py#L221-L270)

### 컬렉션 삭제 (`DELETE /collections/{collection_id}`)
특정 컬렉션을 삭제합니다. 이 작업은 멱등(idempotent)합니다.

**응답 형식 (204 No Content)**:
성공 시 응답 본문 없이 204 상태 코드를 반환합니다.

**Section sources**
- [collections.yaml](file://aperag/api/paths/collections.yaml#L201-L250)
- [collection_service.py](file://aperag/service/collection_service.py#L271-L320)

### 컬렉션 요약 생성 (`POST /collections/{collection_id}/summary/generate`)
백그라운드 작업으로 컬렉션의 요약을 생성하도록 트리거합니다.

**응답 형식 (200 OK)**:
작업 시작 여부를 나타내는 JSON 객체를 반환합니다.
```json
{
  "collection_id": "string",
  "success": true,
  "message": "string",
  "status": "PENDING"
}
```

**Section sources**
- [collections.yaml](file://aperag/api/paths/collections.yaml#L251-L300)
- [collections.py](file://aperag/views/collections.py#L100-L130)

### 컬렉션 공유 설정
*   **공유 상태 조회 (`GET /collections/{collection_id}/sharing`)**: 컬렉션이 마켓플레이스에 게시되었는지 여부를 확인합니다.
*   **게시 (`POST /collections/{collection_id}/sharing`)**: 컬렉션을 마켓플레이스에 게시합니다.
*   **게시 취소 (`DELETE /collections/{collection_id}/sharing`)**: 컬렉션의 마켓플레이스 게시를 취소합니다.

**Section sources**
- [collections.py](file://aperag/views/collections.py#L131-L200)

## 문서 관리 엔드포인트

### 문서 업로드 (`POST /collections/{collection_id}/documents/upload`)
단일 문서 파일을 임시 저장소에 업로드합니다. 이는 대량 업로드 워크플로우의 첫 번째 단계입니다.

**요청 본문**:
`multipart/form-data` 형식으로 `file` 필드에 바이너리 파일을 포함해야 합니다.

**응답 형식 (200 OK)**:
`uploadDocumentResponse` 객체를 반환합니다. 업로드된 문서의 `document_id`, `filename`, `size`, `status`를 포함합니다.

**Section sources**
- [collections.yaml](file://aperag/api/paths/collections.yaml#L700-L750)
- [document.yaml](file://aperag/api/components/schemas/document.yaml#L1-L254)
- [collections.py](file://aperag/views/collections.py#L350-L370)

### 문서 확인 (`POST /collections/{collection_id}/documents/confirm`)
임시 저장소에 업로드된 문서를 컬렉션에 추가하기 위해 확인(confirm)합니다. 이 작업은 문서의 상태를 `UPLOADED`에서 `PENDING`으로 변경하고 인덱싱 프로세스를 시작합니다.

**요청 본문 (confirmDocumentsRequest)**:
확인할 문서 ID 목록을 포함합니다.
```json
{ "document_ids": ["doc_id_1", "doc_id_2"] }
```

**응답 형식 (200 OK)**:
`confirmDocumentsResponse` 객체를 반환합니다. 성공/실패한 문서 수와 실패 이유를 포함합니다.

**Section sources**
- [collections.yaml](file://aperag/api/paths/collections.yaml#L751-L800)
- [document.yaml](file://aperag/api/components/schemas/document.yaml#L1-L254)
- [collections.py](file://aperag/views/collections.py#L371-L390)

### 문서 생성 (`POST /collections/{collection_id}/documents`)
`create_documents` 뷰 함수는 여러 파일을 동시에 업로드하고 생성하는 편의 엔드포인트를 제공합니다. 내부적으로는 업로드 후 즉시 확인하는 로직을 수행합니다.

**Section sources**
- [collections.py](file://aperag/views/collections.py#L280-L300)
- [document_service.py](file://aperag/service/document_service.py#L300-L400)

### 문서 목록 조회 (`GET /collections/{collection_id}/documents`)
특정 컬렉션에 속한 문서들의 페이지네이션된 목록을 조회합니다.

**쿼리 매개변수**:
- `page`, `page_size`: 페이지네이션
- `sort_by`: 정렬 기준 (`name`, `created`, `updated`, `size`, `status`)
- `sort_order`: 정렬 순서 (`asc`, `desc`)
- `search`: 이름으로 문서 검색

**응답 형식 (200 OK)**:
페이지 정보와 함께 `DocumentList` 객체를 반환합니다.

**Section sources**
- [collections.yaml](file://aperag/api/paths/collections.yaml#L301-L350)
- [document_service.py](file://aperag/service/document_service.py#L401-L500)

### 문서 상세 조회 (`GET /collections/{collection_id}/documents/{document_id}`)
특정 문서의 전체 세부 정보를 조회합니다.

**응답 형식 (200 OK)**:
`Document` 객체를 반환합니다. 문서의 상태, 각 인덱스(벡터, 풀텍스트 등)의 상태, 크기 등을 포함합니다.

**Section sources**
- [collections.yaml](file://aperag/api/paths/collections.yaml#L351-L400)
- [document_service.py](file://aperag/service/document_service.py#L501-L520)

### 문서 삭제 (`DELETE /collections/{collection_id}/documents/{document_id}`)
특정 문서를 삭제합니다.

**응답 형식 (204 No Content)**:
성공 시 응답 본문 없이 204 상태 코드를 반환합니다.

**Section sources**
- [collections.yaml](file://aperag/api/paths/collections.yaml#L401-L450)
- [document_service.py](file://aperag/service/document_service.py#L521-L550)

### 인덱스 재생성 (`POST /collections/{collection_id}/rebuild_indexes`)
문서의 특정 유형 인덱스(예: 벡터, 풀텍스트)를 재생성합니다.

**요청 본문 (rebuildIndexesRequest)**:
재생성할 인덱스 유형 배열을 지정합니다.
```json
{ "index_types": ["VECTOR", "FULLTEXT"] }
```

**Section sources**
- [collections.yaml](file://aperag/api/paths/collections.yaml#L451-L500)
- [document_service.py](file://aperag/service/document_service.py#L551-L600)

## 검색 및 지식 그래프 엔드포인트

### 컬렉션 검색 (`POST /collections/{collection_id}/searches`)
지정된 컬렉션 내에서 쿼리를 실행합니다. 벡터, 풀텍스트, 지식 그래프 등 다양한 검색 유형을 조합할 수 있습니다.

**요청 본문 (searchRequest)**:
```json
{
  "query": "검색어",
  "vector_search": { "topk": 5, "similarity": 0.2 },
  "fulltext_search": { "topk": 5, "keywords": ["키워드1", "키워드2"] },
  "graph_search": { "topk": 5 },
  "rerank": true,
  "save_to_history": false
}
```

**응답 형식 (200 OK)**:
`searchResult` 객체를 반환합니다. 검색 아이템 목록, 점수, 출처 등을 포함합니다.

**Section sources**
- [collections.yaml](file://aperag/api/paths/collections.yaml#L501-L550)
- [collection.yaml](file://aperag/api/components/schemas/collection.yaml#L1-L491)
- [collection_service.py](file://aperag/service/collection_service.py#L321-L450)

### 검색 기록 조회 (`GET /collections/{collection_id}/searches`)
해당 컬렉션에서 수행된 검색 기록을 조회합니다.

**Section sources**
- [collections.yaml](file://aperag/api/paths/collections.yaml#L551-L600)
- [collection_service.py](file://aperag/service/collection_service.py#L451-L480)

### 지식 그래프 조회 (`GET /collections/{collection_id}/graphs`)
컬렉션의 지식 그래프 데이터를 조회합니다. 전체 그래프의 개요 모드 또는 특정 노드 중심의 서브그래프 모드를 지원합니다.

**쿼리 매개변수**:
- `label`: 시작 노드의 라벨. `"*"`는 전체 그래프 개요를 의미합니다.
- `max_nodes`: 반환할 최대 노드 수.
- `max_depth`: 서브그래프 탐색의 최대 깊이.

**Section sources**
- [collections.yaml](file://aperag/api/paths/collections.yaml#L601-L650)
- [collections.py](file://aperag/views/collections.py#L391-L418)

## 권한 및 인증 요구사항

모든 컬렉션 및 문서 관련 엔드포인트는 인증이 필요합니다. 인증 방식은 다음과 같습니다:

*   **Bearer 토큰**: 대부분의 엔드포인트는 `security` 섹션에 `BearerAuth`를 요구합니다. 클라이언트는 HTTP 요청 헤더에 `Authorization: Bearer <access_token>`을 포함해야 합니다.
*   **소유자 및 구독자 접근**: 컬렉션에 대한 접근은 두 가지 방식으로 이루어집니다.
    *   **소유자(owner)**: 컬렉션을 생성한 사용자. 모든 CRUD 작업을 수행할 수 있습니다.
    *   **구독자(subscriber)**: 마켓플레이스를 통해 공유된 컬렉션에 접근하는 사용자. 일반적으로 읽기 전용 접근 권한을 가집니다.
*   **공유 설정 제한**: `publish_collection_to_marketplace`와 같은 공유 설정 엔드포인트는 컬렉션의 소유자만 호출할 수 있습니다. 이를 위반하면 `403 Forbidden` 오류가 발생합니다.

**Section sources**
- [collections.yaml](file://aperag/api/paths/collections.yaml#L1-L1304)
- [collections.py](file://aperag/views/collections.py#L1-L418)

## 사용 예제: 컬렉션 생성 및 문서 업로드

다음은 새 컬렉션을 생성한 후 여러 문서를 업로드하는 연동 시나리오입니다.

1.  **컬렉션 생성**: `POST /collections` 엔드포인트를 호출하여 새로운 컬렉션을 만듭니다.
2.  **문서 업로드**: `POST /collections/{new_collection_id}/documents/upload`를 여러 번 호출하여 각 문서를 임시 저장소에 업로드합니다. 각 호출은 고유한 `document_id`를 반환합니다.
3.  **문서 확인**: 이전 단계에서 받은 `document_id` 목록을 사용하여 `POST /collections/{new_collection_id}/documents/confirm` 엔드포인트를 호출합니다. 이로써 모든 문서가 컬렉션에 추가되고 인덱싱이 시작됩니다.

또는, `POST /collections/{collection_id}/documents` 엔드포인트를 사용하여 파일 목록을 한 번에 전송함으로써 위의 2단계와 3단계를 하나의 요청으로 통합할 수 있습니다.

**Section sources**
- [collections.py](file://aperag/views/collections.py#L280-L300)
- [document_service.py](file://aperag/service/document_service.py#L300-L400)

## 오류 처리 전략

API는 표준화된 오류 응답 형식을 사용합니다. 대부분의 오류는 `failResponse` 스키마를 따르며, `4xx` 상태 코드와 함께 다음 구조의 JSON을 반환합니다.

```json
{
  "code": "ERROR_CODE",
  "message": "오류 설명"
}
```

주요 오류 코드 및 상태 코드:
*   `401 Unauthorized`: 유효한 Bearer 토큰이 없는 경우.
*   `404 Not Found`: 요청한 `collection_id` 또는 `document_id`가 존재하지 않는 경우.
*   `400 Bad Request`: 요청 본문이 유효하지 않거나, 파일이 너무 큰 경우.
*   `403 Forbidden`: 리소스에 대한 접근 권한이 없는 경우 (예: 다른 사용자의 컬렉션 수정 시도).
*   `422 Unprocessable Entity`: 요청 본문의 스키마가 유효하지 않은 경우 (FastAPI 기본 오류).

**Section sources**
- [collections.yaml](file://aperag/api/paths/collections.yaml#L1-L1304)
- [common.yaml](file://aperag/api/components/schemas/common.yaml)

## 성능 최적화 팁

*   **대량 문서 처리**: 많은 수의 문서를 컬렉션에 추가할 때는, `upload_document`과 `confirm_documents` 엔드포인트를 사용하는 것이 권장됩니다. 이 분리된 워크플로우는 네트워크 문제나 실패 시 부분적인 복구가 가능하게 하여 더 견고한 처리를 제공합니다.
*   **배치 업로드**: 가능한 경우, `create_documents` 엔드포인트를 사용하여 여러 파일을 한 번의 요청으로 전송하세요. 이는 연결 오버헤드를 줄이고 처리 속도를 향상시킬 수 있습니다.
*   **검색 파라미터 조정**: `searchRequest`에서 `topk` 값을 적절히 설정하여 반환되는 결과 수를 제한함으로써 응답 시간을 개선할 수 있습니다. 불필요한 데이터 전송을 피하세요.
*   **지식 그래프 탐색**: `GET /graphs` 엔드포인트에서 `max_nodes`와 `max_depth`를 신중하게 설정하여 과도한 데이터 로딩을 방지하고 UI 성능을 유지하세요.

**Section sources**
- [document_service.py](file://aperag/service/document_service.py#L300-L400)
- [collections.py](file://aperag/views/collections.py#L280-L300)