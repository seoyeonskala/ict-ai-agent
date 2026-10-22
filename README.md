# ICT 운영 인시던트 진단 AI 에이전트

LangGraph 기반 장애 진단 자동화 에이전트. 사용자가 장애 상황을 입력하면 모니터링 데이터 조회, 런북 검색, 진단 보고서 작성까지 자동으로 수행한다.

## 주요 기술 스택

| 기술 | 용도 |
|------|------|
| LangGraph (StateGraph) | 에이전트 파이프라인 (route → plan → gate → research → replan → analysis → write → validate → finalize) |
| MCP (Model Context Protocol) | 모니터링 Tool 호출, 표준 진단 절차 Prompt 주입 |
| ChromaDB + sentence-transformers | 런북 RAG 벡터 검색 |
| Ollama (qwen3:0.6b / 8b) | 로컬 LLM (Fast/Quality 모델 분리) |
| FastAPI + SSE | 백엔드 API, 실시간 스트리밍 |
| Vue 3 | 브라우저 채팅 UI |
| LangSmith | LLM 호출 추적 및 평가 |
| SQLite | 세션 이력 저장 + 대화 요약 |

## 프로젝트 구조

```
├── server.py                  # FastAPI 백엔드 (포트 8100)
├── web_demo_server.py         # 웹 데모 프록시 서버 (포트 8600)
├── web_chat.html              # Vue 3 채팅 UI
├── mcp_server.py              # MCP 서버 (Tool/Resource/Prompt)
│
├── agent/
│   ├── graph.py               # LangGraph 그래프 조립 (63줄)
│   ├── state.py               # AgentState 타입 정의
│   ├── config.py              # 설정 중앙 관리
│   ├── rag.py                 # ChromaDB 런북 벡터 검색
│   ├── ollama_llm.py          # Ollama LLM 백엔드
│   ├── openai_llm.py          # OpenAI LLM 백엔드
│   ├── fake_llm.py            # 테스트용 결정론적 LLM
│   ├── session_store.py       # SQLite 세션 + 대화 요약
│   ├── nodes/                 # 그래프 노드 모듈
│   │   ├── route.py           # 라우팅 (chat/incident 분류)
│   │   ├── plan.py            # 조사 계획 수립
│   │   ├── gate.py            # 불필요 태스크 제거
│   │   ├── research.py        # 멀티에이전트 디스패처
│   │   ├── analysis.py        # 패턴 분석
│   │   └── write.py           # 보고서 작성/검증/확정
│   └── agents/                # 서브 에이전트
│       ├── monitor_agent.py   # MCP Tool 호출 (모니터링)
│       └── runbook_agent.py   # RAG 검색 (런북)
│
├── eval/                      # 평가 프레임워크
│   ├── test_cases.py          # 테스트 케이스 5건
│   ├── judge.py               # LLM-as-judge
│   └── run_eval.py            # 평가 실행기
│
├── data/
│   ├── monitoring.json        # 시스템 모니터링 데이터
│   └── runbooks/              # 런북 마크다운 파일 (6개)
│
└── sh/                        # 실행 스크립트
```

## 실행 방법

### 1. 환경 준비

```bash
# 가상환경 생성 + 패키지 설치
bash sh/setup_venv.sh

# Ollama 모델 준비
bash sh/setup_ollama.sh
```

### 2. 런북 RAG 인덱싱 (최초 1회)

```bash
bash sh/index_runbooks.sh
```

### 3. 서버 실행

```bash
# 터미널 1 — 백엔드 서버
bash sh/run_agent_ollma.sh

# 터미널 2 — 웹 채팅 UI
python3 web_demo_server.py
```

브라우저에서 `http://localhost:8600` 접속.

### 4. 테스트

```bash
# API 직접 호출
curl -s "http://127.0.0.1:8100/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "auth-service 장애 발생, CPU 급증", "thread_id": "test-1"}' \
  | python3 -m json.tool

# SSE 스트리밍
curl -s "http://127.0.0.1:8100/chat/stream?message=auth-service%20장애%20진단&thread_id=test-2"

# 평가 실행
cd eval && python run_eval.py --judge
```

## 개선 사항 (6건)

| # | 개선 | 내용 |
|---|------|------|
| 1 | 런북 RAG 전환 | MCP Resource 고정 1건 → ChromaDB 벡터 검색 top-5 |
| 2 | 그래프 모듈화 | graph.py 338줄 → 63줄 + nodes/ 6개 모듈 |
| 3 | 멀티에이전트 | 단일 research → MonitorAgent + RunbookAgent 병렬 실행 |
| 4 | 평가 체계 | LLM-as-judge + 키워드 매칭 자동 채점 |
| 5 | 설정 중앙화 | 하드코딩 제거 → config.py + 환경변수 |
| 6 | 대화 요약 | 10턴 이상 시 fast LLM으로 요약 + 최근 4턴만 전달 |

## Before/After 실측 비교

같은 질문("auth-service 장애 발생, CPU 급증, 응답 지연")으로 측정:

| 항목 | Before | After |
|------|--------|-------|
| 병렬 실행 시간 | 0.36초 | 0.17초 (2.1배 향상) |
| 총 비용 | $0.007557 | $0.003844 (49% 절감) |
| retry | 1회 | 0회 |
| 런북 검색 | 고정 1건 | RAG top-5 유사도 검색 |
| 응답 품질 | 일부 수치 인용 | CPU 77%, 메모리 60.5%, connection pool 92% 등 다수 인용 |

## LLM 백엔드 전환

| 백엔드 | 명령 | 비용 |
|--------|------|------|
| Ollama (로컬) | `bash sh/run_agent_ollma.sh` | 무료 |
| OpenAI (API) | `bash sh/run_agent_openai.sh` | 과금 |
| Fake (테스트) | `python3 server.py` | 무료 |

## 참고 문서

- [개선 보고서](doc/improvement_report.md)
- [Before/After 테스트 가이드](doc/before_after_test.md)
- [Ollama 매뉴얼](doc/manual_ollma.md)
- [OpenAI 매뉴얼](doc/manual_openai.md)
