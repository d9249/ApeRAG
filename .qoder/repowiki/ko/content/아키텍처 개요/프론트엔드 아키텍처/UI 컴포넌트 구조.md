# UI 컴포넌트 구조

<cite>
**이 문서에서 참조된 파일**
- [button.tsx](file://web/src/components/ui/button.tsx)
- [input.tsx](file://web/src/components/ui/input.tsx)
- [card.tsx](file://web/src/components/ui/card.tsx)
- [table.tsx](file://web/src/components/ui/table.tsx)
- [chat-input.tsx](file://web/src/components/chat/chat-input.tsx)
- [chat-messages.tsx](file://web/src/components/chat/chat-messages.tsx)
</cite>

## 목차
1. [소개](#소개)
2. [프로젝트 구조](#프로젝트-구조)
3. [핵심 구성 요소](#핵심-구성-요소)
4. [아키텍처 개요](#아키텍처-개요)
5. [상세 구성 요소 분석](#상세-구성-요소-분석)
6. [의존성 분석](#의존성-분석)

## 소개
ApeRAG 프로젝트는 그래프 기반 RAG(Retrieval-Augmented Generation), 벡터 검색, 풀텍스트 검색을 결합한 프로덕션 준비 완료된 AI 플랫폼입니다. 이 문서는 `web/src/components` 디렉토리에 위치한 UI 컴포넌트들의 계층적 구조를 설명하며, 원자성 컴포넌트부터 고차원 채팅 인터페이스까지의 아키텍처와 설계 원칙을 분석합니다.

## 프로젝트 구조
UI 컴포넌트는 `web/src/components` 디렉토리 아래에 계층적으로 구성되어 있습니다. 주요 디렉토리는 다음과 같습니다:

- `ui/`: 버튼, 입력 필드, 카드, 테이블 등 재사용 가능한 원자성 컴포넌트들
- `chat/`: 채팅 인터페이스 관련 고차원 컴포넌트들
- `providers/`: 상태 관리 및 컨텍스트 제공자
- `app-topbar.tsx`, `page-container.tsx`: 애플리케이션 전반의 레이아웃 컴포넌트

```mermaid
graph TB
subgraph "UI Components"
A[ui/] --> B[button.tsx]
A --> C[input.tsx]
A --> D[card.tsx]
A --> E[table.tsx]
A --> F[form.tsx]
A --> G[dialog.tsx]
A --> H[alert.tsx]
end
subgraph "Chat Components"
I[chat/] --> J[chat-input.tsx]
I --> K[chat-messages.tsx]
I --> L[message-parts-ai.tsx]
I --> M[message-parts-user.tsx]
end
subgraph "Layout & Providers"
N[app-topbar.tsx]
O[page-container.tsx]
P[providers/bot-provider.tsx]
end
J --> |사용| B
J --> |사용| C
J --> |사용| F
K --> |사용| J
K --> |사용| L
K --> |사용| M
```

**Diagram sources**
- [web/src/components/ui/button.tsx](file://web/src/components/ui/button.tsx)
- [web/src/components/ui/input.tsx](file://web/src/components/ui/input.tsx)
- [web/src/components/ui/card.tsx](file://web/src/components/ui/card.tsx)
- [web/src/components/ui/table.tsx](file://web/src/components/ui/table.tsx)
- [web/src/components/chat/chat-input.tsx](file://web/src/components/chat/chat-input.tsx)
- [web/src/components/chat/chat-messages.tsx](file://web/src/components/chat/chat-messages.tsx)

**Section sources**
- [web/src/components/ui](file://web/src/components/ui)
- [web/src/components/chat](file://web/src/components/chat)

## 핵심 구성 요소

### 원자성 UI 컴포넌트
`ui/` 디렉토리에는 Tailwind CSS와 class-variance-authority(cva)를 활용하여 스타일링된 재사용 가능한 원자성 컴포넌트들이 포함되어 있습니다. 이러한 컴포넌트들은 일관된 디자인 시스템을 제공하며, 접근성(a11y) 요구사항을 준수합니다.

### 고차원 채팅 컴포넌트
`chat/` 디렉토리에는 채팅 인터페이스를 구성하는 고차원 컴포넌트들이 위치해 있습니다. `chat-input`과 `chat-messages` 컴포넌트는 사용자 상호작용과 메시지 렌더링의 핵심 역할을 수행합니다.

**Section sources**
- [web/src/components/ui/button.tsx](file://web/src/components/ui/button.tsx#L1-L61)
- [web/src/components/chat/chat-input.tsx](file://web/src/components/chat/chat-input.tsx#L1-L600)

## 아키텍처 개요

```mermaid
graph TD
subgraph "Client Components"
CI[chat-input.tsx]
CM[chat-messages.tsx]
MPI[message-parts-ai.tsx]
MPU[message-parts-user.tsx]
end
subgraph "Atomic UI Components"
BU[button.tsx]
IN[input.tsx]
CA[card.tsx]
TA[table.tsx]
ME[mention.tsx]
FI[file-upload.tsx]
TO[tooltip.tsx]
SE[select.tsx]
end
subgraph "State Management"
BP[bot-provider.tsx]
LS[useLocalStorageState]
WS[useWebSocket]
end
subgraph "API Layer"
AC[apiClient]
end
CI --> BU
CI --> IN
CI --> ME
CI --> FI
CI --> TO
CI --> SE
CM --> CI
CM --> MPI
CM --> MPU
CI --> BP
CM --> BP
CM --> WS
CI --> AC
CM --> AC
```

**Diagram sources**
- [web/src/components/chat/chat-input.tsx](file://web/src/components/chat/chat-input.tsx)
- [web/src/components/chat/chat-messages.tsx](file://web/src/components/chat/chat-messages.tsx)
- [web/src/components/ui/button.tsx](file://web/src/components/ui/button.tsx)
- [web/src/components/providers/bot-provider.tsx](file://web/src/components/providers/bot-provider.tsx)

## 상세 구성 요소 분석

### 원자성 컴포넌트 분석

#### Button 컴포넌트
버튼 컴포넌트는 cva 라이브러리를 사용하여 다양한 변형(variant)과 크기(size) 옵션을 제공합니다. 기본, 파괴적, 외곽선, 보조, ghost, 링크 등 6가지 변형과 기본, 소형, 대형, 아이콘 등 4가지 크기 옵션이 정의되어 있습니다.

```mermaid
classDiagram
class Button {
+className : string
+variant : "default"|"destructive"|"outline"|"secondary"|"ghost"|"link"
+size : "default"|"sm"|"lg"|"icon"
+asChild : boolean
+...props : React.ComponentProps<'button'>
}
Button : +render() JSX.Element
```

**Diagram sources**
- [web/src/components/ui/button.tsx](file://web/src/components/ui/button.tsx#L42-L58)

**Section sources**
- [web/src/components/ui/button.tsx](file://web/src/components/ui/button.tsx#L1-L61)

#### Input 컴포넌트
입력 필드 컴포넌트는 접근성과 반응형 디자인을 고려하여 설계되었습니다. 포커스 상태, 유효성 검사 오류 상태 등을 위한 적절한 스타일링과 aria-invalid 속성을 포함하고 있습니다.

```mermaid
classDiagram
class Input {
+className : string
+type : string
+...props : React.ComponentProps<'input'>
}
Input : +render() JSX.Element
```

**Diagram sources**
- [web/src/components/ui/input.tsx](file://web/src/components/ui/input.tsx#L4-L18)

**Section sources**
- [web/src/components/ui/input.tsx](file://web/src/components/ui/input.tsx#L1-L22)

#### Card 컴포넌트
카드 컴포넌트는 헤더, 본문, 바닥글 등의 하위 컴포넌트와 함께 사용되는 컨테이너 역할을 합니다. 그림자 효과와 여백을 통해 콘텐츠를 시각적으로 그룹화합니다.

```mermaid
classDiagram
class Card {
+className : string
+...props : React.ComponentProps<'div'>
}
class CardHeader {
+className : string
+...props : React.ComponentProps<'div'>
}
class CardTitle {
+className : string
+...props : React.ComponentProps<'div'>
}
class CardDescription {
+className : string
+...props : React.ComponentProps<'div'>
}
class CardContent {
+className : string
+...props : React.ComponentProps<'div'>
}
class CardFooter {
+className : string
+...props : React.ComponentProps<'div'>
}
Card --> CardHeader
Card --> CardContent
Card --> CardFooter
CardHeader --> CardTitle
CardHeader --> CardDescription
```

**Diagram sources**
- [web/src/components/ui/card.tsx](file://web/src/components/ui/card.tsx#L4-L15)

**Section sources**
- [web/src/components/ui/card.tsx](file://web/src/components/ui/card.tsx#L1-L93)

#### Table 컴포넌트
테이블 컴포넌트는 반응형 디자인을 위해 외부 div 컨테이너를 사용하여 수평 스크롤을 지원합니다. 헤더, 본문, 바닥글, 행, 셀 등의 하위 컴포넌트로 구성되어 있으며, hover 상태와 선택 상태를 위한 스타일링도 포함되어 있습니다.

```mermaid
classDiagram
class Table {
+className : string
+...props : React.ComponentProps<'table'>
}
class TableHeader {
+className : string
+...props : React.ComponentProps<'thead'>
}
class TableBody {
+className : string
+...props : React.ComponentProps<'tbody'>
}
class TableRow {
+className : string
+...props : React.ComponentProps<'tr'>
}
class TableHead {
+className : string
+...props : React.ComponentProps<'th'>
}
class TableCell {
+className : string
+...props : React.ComponentProps<'td'>
}
Table --> TableHeader
Table --> TableBody
Table --> TableFooter
TableHeader --> TableRow
TableBody --> TableRow
TableRow --> TableHead
TableRow --> TableCell
```

**Diagram sources**
- [web/src/components/ui/table.tsx](file://web/src/components/ui/table.tsx#L6-L19)

**Section sources**
- [web/src/components/ui/table.tsx](file://web/src/components/ui/table.tsx#L1-L117)

### 고차원 채팅 컴포넌트 분석

#### ChatInput 컴포넌트
채팅 입력 컴포넌트는 사용자의 쿼리를 입력받고 제출하는 핵심 인터페이스입니다. 이 컴포넌트는 여러 원자성 컴포넌트들을 조합하여 복잡한 기능을 제공합니다.

```mermaid
sequenceDiagram
participant User as 사용자
participant CI as ChatInput
participant API as API 클라이언트
User->>CI : 메시지 입력
CI->>CI : 입력 내용 상태 저장
User->>CI : 파일 첨부
CI->>CI : 첨부 파일 상태 관리
User->>CI : 모델 선택
CI->>CI : 로컬 스토리지에 모델 이름 저장
User->>CI : 웹 검색 활성화
CI->>CI : 로컬 스토리지에 설정 저장
User->>CI : 전송 버튼 클릭
CI->>CI : 입력 유효성 검사
CI->>CI : 제출 데이터 구성
CI->>API : 채팅 문서 업로드 요청
API-->>CI : 문서 ID 반환
CI->>API : 채팅 연결 요청
API-->>CI : 메시지 전송 성공
```

**Diagram sources**
- [web/src/components/chat/chat-input.tsx](file://web/src/components/chat/chat-input.tsx#L81-L598)

**Section sources**
- [web/src/components/chat/chat-input.tsx](file://web/src/components/chat/chat-input.tsx#L1-L600)

#### ChatMessages 컴포넌트
채팅 메시지 컴포넌트는 메시지 기록을 렌더링하고 실시간 메시지를 처리하는 역할을 합니다. WebSocket을 통해 서버로부터 실시간으로 메시지 조각을 수신하고, 이를 누적하여 표시합니다.

```mermaid
flowchart TD
Start([컴포넌트 마운트]) --> Init["초기 상태 설정<br/>- messages: chat.history<br/>- loading: false"]
Init --> ConnectWS["WebSocket 연결 설정"]
ConnectWS --> OnMessage["onMessage 이벤트 리스너 등록"]
OnMessage --> ParseMsg["메시지 파싱<br/>JSON.parse(message.data)"]
ParseMsg --> CheckType{"메시지 타입 확인"}
CheckType --> |start| SetLoading["loading = true"]
SetLoading --> AddStartPart["messages에 시작 부분 추가"]
CheckType --> |message| FindParts{"기존 메시지 조각 찾기"}
FindParts --> |존재| UpdateData["기존 조각에 데이터 추가"]
FindParts --> |미존재| CreateNew["새 메시지 조각 생성"]
CheckType --> |stop| SetNotLoading["loading = false"]
SetNotLoading --> AddReferences["참조 정보 추가"]
SetNotLoading --> RenameChat["채팅 이름 갱신"]
CheckType --> |기타| FindPartById{"part_id로 조각 찾기"}
FindPartById --> |존재| AppendData["기존 조각에 데이터 추가"]
FindPartById --> |미존재| AddNewPart["새 조각 추가"]
UpdateData --> Render["화면 렌더링"]
CreateNew --> Render
AddNewPart --> Render
AddStartPart --> Render
AddReferences --> Render
Render --> Scroll["하단으로 스크롤"]
Scroll --> Wait["다음 메시지 대기"]
Wait --> OnMessage
```

**Diagram sources**
- [web/src/components/chat/chat-messages.tsx](file://web/src/components/chat/chat-messages.tsx#L18-L240)

**Section sources**
- [web/src/components/chat/chat-messages.tsx](file://web/src/components/chat/chat-messages.tsx#L1-L242)

## 의존성 분석

```mermaid
graph TD
CI[chat-input.tsx] --> BU[button.tsx]
CI --> IN[input.tsx]
CI --> ME[mention.tsx]
CI --> FI[file-upload.tsx]
CI --> TO[tooltip.tsx]
CI --> SE[select.tsx]
CI --> LA[label.tsx]
CI --> TE[textarea.tsx]
CI --> TOG[toggle.tsx]
CM[chat-messages.tsx] --> CI[chat-input.tsx]
CM --> MPI[message-parts-ai.tsx]
CM --> MPU[message-parts-user.tsx]
CI --> BP[bot-provider.tsx]
CM --> BP[bot-provider.tsx]
CI --> LS[useLocalStorageState]
CI --> INT[ahooks/useInterval]
CM --> WS[ahooks/useWebSocket]
CM --> RS[react-scroll]
CI --> AC[apiClient]
CM --> AC[apiClient]
style CI fill:#f9f,stroke:#333
style CM fill:#f9f,stroke:#333
```

**Diagram sources**
- [web/src/components/chat/chat-input.tsx](file://web/src/components/chat/chat-input.tsx)
- [web/src/components/chat/chat-messages.tsx](file://web/src/components/chat/chat-messages.tsx)

**Section sources**
- [web/src/components/chat/chat-input.tsx](file://web/src/components/chat/chat-input.tsx)
- [web/src/components/chat/chat-messages.tsx](file://web/src/components/chat/chat-messages.tsx)