# Helm 기반 애플리케이션 배포

<cite>
**이 문서에서 참조한 파일**  
- [Chart.yaml](file://deploy/aperag/Chart.yaml)
- [values.yaml](file://deploy/aperag/values.yaml)
- [api-deployment.yaml](file://deploy/aperag/templates/api-deployment.yaml)
- [celeryworker-deployment.yaml](file://deploy/aperag/templates/celeryworker-deployment.yaml)
- [frontend-deployment.yaml](file://deploy/aperag/templates/frontend-deployment.yaml)
- [ingress.yaml](file://deploy/aperag/templates/ingress.yaml)
- [frontend-configmap.yaml](file://deploy/aperag/templates/frontend-configmap.yaml)
- [postgresql/values.yaml](file://deploy/databases/postgresql/values.yaml)
- [redis/values.yaml](file://deploy/databases/redis/values.yaml)
- [qdrant/values.yaml](file://deploy/databases/qdrant/values.yaml)
</cite>

## 목차
1. [소개](#소개)  
2. [프로젝트 구조](#프로젝트-구조)  
3. [차트 메타데이터 및 종속성 분석](#차트-메타데이터-및-종속성-분석)  
4. [values.yaml을 통한 구성 커스터마이징](#valuesyaml을-통한-구성-커스터마이징)  
5. [템플릿 매니페스트 생성 로직](#템플릿-매니페스트-생성-로직)  
6. [배포 전략 및 실습 예제](#배포-전략-및-실습-예제)  
7. [결론](#결론)

## 소개
ApeRAG는 RAG(Retrieval-Augmented Generation) 기반의 지능형 챗봇 플랫폼으로, Helm 차트를 통해 쿠버네티스 환경에 효율적으로 배포할 수 있습니다. 본 문서는 ApeRAG Helm 차트를 사용하여 API 서버, Celery 워커, 프론트엔드, 인그레스 등을 포함한 전체 애플리케이션 스택을 쿠버네티스 클러스터에 배포하는 절차를 상세히 설명합니다. 또한 Chart.yaml과 values.yaml의 구조, 템플릿 변수 치환 방식, 리소스 설정, 롤링 업데이트 전략까지 다룹니다.

## 프로젝트 구조
ApeRAG의 Helm 차트는 `deploy/aperag` 디렉터리에 위치하며, 다음과 같은 주요 구성 요소로 이루어져 있습니다:

```
deploy/aperag/
├── Chart.yaml          # 차트 메타데이터 정의
├── values.yaml         # 기본 구성 값 정의
├── templates/          # Kubernetes 매니페스트 템플릿
│   ├── api-deployment.yaml
│   ├── celeryworker-deployment.yaml
│   ├── frontend-deployment.yaml
│   ├── ingress.yaml
│   └── frontend-configmap.yaml
└── ...
```

또한 데이터베이스 별도의 Helm 차트들이 `deploy/databases/` 하위에 존재하며, PostgreSQL, Redis, Qdrant 등 각각 독립된 values.yaml을 통해 구성됩니다.

**Section sources**
- [Chart.yaml](file://deploy/aperag/Chart.yaml#L1-L25)
- [values.yaml](file://deploy/aperag/values.yaml#L1-L392)

## 차트 메타데이터 및 종속성 분석
`Chart.yaml`은 Helm 차트의 핵심 메타데이터를 정의합니다. ApeRAG 차트는 `application` 타입으로, 실제 배포 가능한 애플리케이션임을 나타냅니다.

```yaml
apiVersion: v2
name: aperag
type: application
version: 0.1.0
appVersion: "0.1.1"
```

- **apiVersion**: Helm 3 이상을 위한 v2 형식
- **name**: 차트 이름 (aperag)
- **type**: application — 실제 배포 가능한 애플리케이션
- **version**: 차트 자체의 버전 (Semantic Versioning 준수)
- **appVersion**: 배포되는 애플리케이션의 버전

현재 차트는 외부 종속성(예: `dependencies:` 섹션)을 명시적으로 선언하지 않으며, 대신 `values.yaml` 내에서 데이터베이스 통합 여부를 `enabled` 플래그로 제어합니다.

**Section sources**
- [Chart.yaml](file://deploy/aperag/Chart.yaml#L1-L25)

## values.yaml을 통한 구성 커스터마이징
`values.yaml`은 ApeRAG 애플리케이션의 모든 구성 요소를 중앙에서 관리하는 핵심 파일입니다. 다음은 주요 구성 항목들입니다.

### 데이터베이스 통합 설정
PostgreSQL, Redis, Elasticsearch, Neo4j, NebulaGraph 등의 데이터베이스 연결 정보를 안전하게 관리할 수 있습니다.

```yaml
postgres:
  enabled: true
  POSTGRES_HOST: "pg-cluster-postgresql-postgresql"
  POSTGRES_CREDENTIALS_SECRET_NAME: "pg-cluster-postgresql-account-postgres"
  POSTGRES_USER: "postgres"
  POSTGRES_PASSWORD: ""
```

- 비밀번호는 직접 설정하지 않고, `POSTGRES_CREDENTIALS_SECRET_NAME`을 통해 쿠버네티스 Secret에서 가져오는 것이 권장됩니다.
- Redis, Elasticsearch 등 다른 DB도 동일한 패턴을 따릅니다.

### API 서버 구성
API 서버의 복제본 수, 리소스 요청/제한, 프로브 설정 등을 포함합니다.

```yaml
api:
  replicaCount: 1
  resources: {}
  livenessProbe:
    httpGet:
      path: /health
      port: 8000
    initialDelaySeconds: 10
  readinessProbe:
    httpGet:
      path: /health
      port: 8000
    initialDelaySeconds: 5
  env:
    JWT_SECRET: "a-very-secret-key-that-you-should-change"
    VECTOR_DB_TYPE: qdrant
    OBJECT_STORE_TYPE: local
```

- `affinity` 설정을 통해 API와 Celery 워커가 동일한 노드에 스케줄되도록 보장합니다.
- `livenessProbe`와 `readinessProbe`는 `/health` 엔드포인트를 통해 상태를 확인합니다.

### Celery 워커 구성
백그라운드 작업 처리를 담당하는 Celery 워커의 설정입니다.

```yaml
celery-worker:
  replicaCount: 1
  embeddingDevice: "cpu"
  livenessProbe:
    exec:
      command:
        - sh
        - -c
        - "celery -A config.celery status -d celery@$(hostname) > /dev/null 2>&1"
```

- `embeddingDevice`를 `cpu` 또는 `gpu`로 설정 가능
- Celery 상태를 직접 체크하는 커스텀 liveness probe 사용

### 프론트엔드 구성
프론트엔드 이미지, 리소스, 로고, 타이틀 등을 설정합니다.

```yaml
frontend:
  replicaCount: 1
  image:
    repository: "docker.io/apecloud/aperag-frontend"
    tag: "v0.0.0-nightly"
  title: "ApeRAG"
  github: "https://github.com/apecloud/ApeRAG"
```

- `frontend-configmap.yaml` 템플릿을 통해 `settings.js` 파일이 ConfigMap으로 생성됨

### DocRay 구성
문서 파싱을 위한 DocRay 서비스의 GPU/CPU 리소스 설정

```yaml
docray:
  enabled: true
  gpu:
    enabled: false
    resources:
      requests:
        nvidia.com/gpu: "1"
  resources:
    requests:
      cpu: "4"
      memory: "10Gi"
```

- GPU 사용 시 `gpu.enabled: true` 및 적절한 nodeSelector/tolerations 설정 필요

**Section sources**
- [values.yaml](file://deploy/aperag/values.yaml#L1-L392)

## 템플릿 매니페스트 생성 로직
Helm 템플릿은 `values.yaml`의 값을 바탕으로 실제 Kubernetes 리소스를 동적으로 생성합니다.

### API Deployment 생성 로직
`templates/api-deployment.yaml`은 `.Values.api.replicaCount`를 기반으로 복제본 수를 설정하고, 조건부로 데이터베이스 환경 변수를 주입합니다.

```yaml
spec:
  replicas: {{ .Values.api.replicaCount }}
  template:
    spec:
      containers:
        - name: aperag-api
          env:
            {{- if .Values.postgres.enabled }}
            - name: POSTGRES_HOST
              value: {{ .Values.postgres.POSTGRES_HOST | quote }}
            {{- end }}
```

- `{{- if }}` 블록을 사용해 데이터베이스 통합 여부에 따라 환경 변수 동적 삽입
- `valueFrom.secretKeyRef`를 사용해 비밀정보는 Secret에서 가져옴
- `volumeMounts`를 통해 `/data` 경로를 hostPath로 공유

**Diagram sources**
- [api-deployment.yaml](file://deploy/aperag/templates/api-deployment.yaml#L1-L224)

### Celery Worker Deployment 생성 로직
Celery 워커는 API와 동일한 이미지를 사용하지만, 시작 스크립트와 환경 변수가 다릅니다.

```yaml
command:
  - /bin/sh
  - -c
  - |
    /app/scripts/entrypoint.sh /app/scripts/start-celery-worker.sh
```

- `index .Values "celery-worker" "replicaCount"`처럼 하이픈 포함 키 접근 시 `index` 함수 사용
- `EMBEDDING_DEVICE` 환경 변수로 CPU/GPU 동작 제어

**Diagram sources**
- [celeryworker-deployment.yaml](file://deploy/aperag/templates/celeryworker-deployment.yaml#L1-L210)

### 프론트엔드 ConfigMap 생성
`frontend-configmap.yaml`은 `values.yaml`의 프론트엔드 설정을 JavaScript 객체 형태의 ConfigMap으로 변환합니다.

```yaml
data:
  settings.js: |
    const APERAG_CONFIG = {
      title: {{ .Values.frontend.title | default "ApeRAG" | quote }},
      github: {{ .Values.frontend.github | default "https://github.com/apecloud/ApeRAG" | quote }},
    }
```

- Helm 템플릿 문법을 사용해 YAML 값을 JS 코드에 삽입
- `default` 필터로 기본값 제공

**Diagram sources**
- [frontend-configmap.yaml](file://deploy/aperag/templates/frontend-configmap.yaml#L1-L23)

### 인그레스 설정
`ingress.yaml`은 `/api`, `/mcp`, `/` 경로를 각각 백엔드 서비스에 매핑합니다.

```yaml
rules:
- http:
    paths:
    - path: "/api"
      backend:
        service:
          name: aperag
          port: { number: 8000 }
    - path: "/"
      backend:
        service:
          name: aperag-frontend
          port: { number: 3000 }
```

- `pathType: Prefix`로 접두사 기반 라우팅
- 선택적으로 `host` 기반 가상 호스팅 지원

**Diagram sources**
- [ingress.yaml](file://deploy/aperag/templates/ingress.yaml#L1-L41)

## 배포 전략 및 실습 예제
### 네임스페이스 격리 전략
각 환경(dev/staging/prod)을 별도의 네임스페이스로 분리하여 배포합니다.

```bash
kubectl create namespace aperag-prod
helm install aperag ./deploy/aperag -n aperag-prod \
  -f custom-values-prod.yaml
```

### 롤링 업데이트 및 롤백
Deployment의 `strategy.type: RollingUpdate` 설정을 통해 무중단 배포가 가능합니다.

```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1
    maxUnavailable: 0
```

업데이트 후 문제가 발생하면 즉시 롤백:

```bash
helm list -n aperag-prod
helm rollback aperag 3 -n aperag-prod
```

### 리소스 조정 예제
CPU 및 메모리 요청/제한을 추가하려면 `values.yaml` 수정:

```yaml
api:
  resources:
    requests:
      cpu: 500m
      memory: 1Gi
    limits:
      cpu: 1000m
      memory: 2Gi
```

### Replica 수 조정
트래픽 증가 시 replica 수 확장:

```yaml
api:
  replicaCount: 3
celery-worker:
  replicaCount: 2
```

### 프로브 설정 조정
응답 속도가 느린 환경을 위해 프로브 지연 시간 조정:

```yaml
livenessProbe:
  initialDelaySeconds: 30
  periodSeconds: 20
readinessProbe:
  initialDelaySeconds: 15
  periodSeconds: 10
```

**Section sources**
- [api-deployment.yaml](file://deploy/aperag/templates/api-deployment.yaml#L1-L224)
- [celeryworker-deployment.yaml](file://deploy/aperag/templates/celeryworker-deployment.yaml#L1-L210)
- [frontend-deployment.yaml](file://deploy/aperag/templates/frontend-deployment.yaml#L1-L64)
- [values.yaml](file://deploy/aperag/values.yaml#L1-L392)

## 결론
ApeRAG의 Helm 차트는 모듈화되고 유연한 구조를 통해 쿠버네티스 환경에서 안정적인 배포를 가능하게 합니다. `Chart.yaml`을 통한 메타데이터 관리, `values.yaml`을 통한 중앙 집중식 구성, 그리고 Go Template 기반의 동적 매니페스트 생성은 운영의 일관성과 재현성을 보장합니다. 또한 네임스페이스 격리, 롤링 업데이트, 리소스 조정 등 현대적인 DevOps 요구사항을 충족할 수 있는 강력한 기반을 제공합니다. 프로덕션 배포 시에는 반드시 비밀정보를 Secret으로 관리하고, 리소스 요청/제한을 적절히 설정하여 안정성을 확보해야 합니다.