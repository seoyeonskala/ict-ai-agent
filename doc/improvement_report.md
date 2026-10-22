# 프로젝트 개선 보고서

> **프로젝트**: all_total_vue — 운영 인시던트 대응 에이전트  
> **작성일**: 2026-10-21  

---

## 1. 개선 개요

기존 프로젝트는 LangGraph 기반 장애 진단 에이전트로, MCP 서버를 통해 모니터링 데이터 조회와 런북 참조를 수행하는 구조였다. 이번 개선에서는 **코드 구조, 데이터 조회 방식, 평가 체계, 설정 관리, 메모리 관리** 총 6개 영역을 개선하였다.

| # | 영역 | 개선 내용 | 상태 |
|---|---|---|---|
| 1 | 데이터 조회 | Runbook RAG 방식 전환 | 완료 |
| 2 | 코드 구조 | Graph 노드 모듈화 | 완료 |
| 3 | 코드 구조 | Research 멀티 에이전트화 | 완료 |
| 4 | 평가 | 평가지표 확장 (LLM-as-judge) | 완료 |
| 5 | 설정 관리 | 하드코딩 영역 개선 | 완료 |
| 6 | 메모리 | Context 관리 (대화 요약) | 완료 |

---

## 2. 개선 상세

### 2.1 Runbook RAG 방식 전환

**문제점**  
기존에는 MCP Resource(`runbook://incident-response/{type}`)를 통해 장애 유형을 정확히 지정해야만 런북을 조회할 수 있었다. 장애 유형 분류가 틀리면 잘못된 런북을 가져오거나 아예 못 가져오는 문제가 있었고, 런북 전체를 LLM에 넘기므로 불필요한 토큰 소비가 발생했다.

**개선 내용**  
ChromaDB + sentence-transformers(all-MiniLM-L6-v2)를 도입하여 벡터 유사도 검색 기반 RAG로 전환하였다.

- 런북 .md 파일을 절차 번호 단위로 청크 분할 → 임베딩 → ChromaDB에 저장
- 런타임에는 사용자 쿼리(증상 텍스트)로 유사도 검색하여 관련 청크만 반환
- score threshold(0.3) 이상인 결과만 필터링

**추가/변경 파일**

| 파일 | 변경 |
|---|---|
| `agent/rag.py` | 신규 — ChromaDB 인덱싱 + 벡터 검색 모듈 |
| `sh/index_runbooks.sh` | 신규 — 인덱싱 실행 스크립트 |
| `requirements.txt` | `chromadb>=0.5`, `sentence-transformers>=3.0` 추가 |
| `agent/nodes/research.py` | MCP Resource 직접 호출 → `search_runbooks()` RAG 검색으로 교체 |

**사용법**
```bash
bash sh/index_runbooks.sh   # 최초 1회 인덱싱 (28개 청크 생성)
```

**효과**
- 장애 유형을 정확히 분류하지 않아도 증상만으로 관련 절차를 검색
- 필요한 청크만 LLM에 전달하여 토큰 절약
- `_classify_incident_type()` 규칙 기반 분류 코드 제거 → 코드 단순화

---

### 2.2 Graph 노드 모듈화

**문제점**  
`agent/graph.py` 하나에 상태 정의, 노드 함수 10개, 헬퍼 함수, 그래프 조립 코드가 모두 포함되어 339줄에 달했다. 노드 추가/수정 시 파일 전체를 파악해야 하며, 테스트와 재사용이 어려웠다.

**개선 내용**  
역할별로 파일을 분리하고, graph.py는 그래프 조립만 담당하도록 변경하였다.

```
변경 전:
  agent/graph.py (339줄) — 모든 것이 한 파일에

변경 후:
  agent/state.py           — AgentState 타입 + add_cost 헬퍼
  agent/graph.py (62줄)    — build_graph + 라우팅 함수만
  agent/nodes/
    __init__.py            — 전체 re-export
    route.py               — route_node, chat_answer_node
    plan.py                — plan_node + 시스템명 추출 헬퍼
    gate.py                — gate_node
    research.py            — research_node, replan_check_node
    analysis.py            — analysis_node
    write.py               — write_node, validate_node, finalize_node
```

**효과**
- graph.py 339줄 → 62줄 (82% 감소)
- 노드별 독립 테스트 가능
- 새 노드 추가 시 기존 코드 영향 최소화
- server.py 수정 불필요 (import 경로 변경 없음)

---

### 2.3 Research 멀티 에이전트화

**문제점**  
`research_node` 하나의 `run_one()` 함수 안에서 if/else로 모니터링 조회와 런북 검색을 분기 처리하고 있었다. 각 역할을 독립적으로 확장하거나 테스트하기 어려웠다.

**개선 내용**  
모니터링 전담과 런북 전담 에이전트를 각각 독립 클래스로 분리하고, research_node는 두 에이전트에 태스크를 분배하는 dispatcher로 변경하였다.

```
변경 전:
  research_node → run_one() 안에서 if monitoring / else runbook

변경 후:
  research_node (dispatcher)
    ├─ MonitorAgent.run(tasks)  ─┐
    │                             ├─ asyncio.gather (병렬)
    └─ RunbookAgent.run(tasks)  ─┘
    → 결과 합치기
```

**추가/변경 파일**

| 파일 | 역할 | 의존성 |
|---|---|---|
| `agent/agents/monitor_agent.py` | MCP Tool로 시스템 상태 조회 + 재시도 | MCP (deps) |
| `agent/agents/runbook_agent.py` | RAG 벡터 검색으로 런북 조회 | RAG (rag.py) |
| `agent/nodes/research.py` | 에이전트 생성 + 병렬 실행 + 결과 병합 | 두 에이전트 |

**효과**
- 각 에이전트를 독립적으로 테스트/교체 가능
- 그래프 구조는 변경 없음 (외부에서는 여전히 research_node 하나)
- 새로운 조사 유형 추가 시 에이전트 클래스만 추가하면 됨

---

### 2.4 평가지표 확장 (LLM-as-judge)

**문제점**  
기존에 체계적인 평가 시스템이 없어, 에이전트 응답 품질을 정량적으로 측정할 수 없었다.

**개선 내용**  
3가지 평가 지표를 측정하는 평가 프레임워크를 구축하였다.

| 지표 | 측정 방식 | 범위 |
|---|---|---|
| 라우트 정확도 | chat/incident 분기 일치 여부 | O/X |
| 키워드 매칭 | 응답에 기대 키워드 포함 비율 | 0.0 ~ 1.0 |
| LLM-as-judge | LLM이 수치 인용 정확성, 절차 구체성 등 채점 | 1 ~ 5점 |

LLM-as-judge는 `backend` 파라미터로 Ollama(기본)와 OpenAI를 전환할 수 있다.

**추가 파일**

| 파일 | 역할 |
|---|---|
| `eval/__init__.py` | 패키지 초기화 |
| `eval/test_cases.py` | 테스트 케이스 5건 (쿼리 + 기대 키워드 + judge 기준) |
| `eval/judge.py` | LLM-as-judge 모듈 (ollama/openai 전환 가능) |
| `eval/run_eval.py` | 평가 실행기 — 서버에 쿼리 → 채점 → JSON 결과 저장 |

**사용법**
```bash
# 에이전트 서버가 떠 있는 상태에서
cd eval
python run_eval.py                          # 키워드 매칭만
python run_eval.py --judge                  # + LLM-as-judge (ollama)
python run_eval.py --judge --backend openai # + LLM-as-judge (openai)
```

---

### 2.5 하드코딩 영역 개선

**문제점**  
`"auth-service"`, `"get_monitoring_status"`, `"http://127.0.0.1:11434/api/chat"` 등의 값이 `ollama_llm.py`, `openai_llm.py`, `nodes/plan.py`, `supervisor_v1.py` 등 여러 파일에 중복으로 하드코딩되어 있었다. `_load_known_systems()`, `_guess_target()`, `_guess_targets()` 함수도 3개 파일에서 동일한 코드가 반복되고 있었다.

**개선 내용**  
`agent/config.py`를 신설하여 모든 설정값과 공통 함수를 한 곳에서 관리하도록 변경하였다.

| 하드코딩 값 | 이전 | 이후 |
|---|---|---|
| `"auth-service"` 디폴트 시스템 | 3개 파일에 각각 | `config.DEFAULT_SYSTEM` (환경변수 변경 가능) |
| `"http://127.0.0.1:11434/api/chat"` | `ollama_llm.py` | `config.OLLAMA_URL` (환경변수 변경 가능) |
| `"incident_analysis_prompt"` | `nodes/plan.py` | `config.MCP_PROMPT_NAME` |
| `"get_monitoring_status"` | 2개 파일 | `config.MCP_TOOL_MONITORING` |
| `{"auth-service", "web-01"}` 폴백 | 3개 파일 | `config.load_known_systems()` 한 곳 |
| `_guess_target()` / `_guess_targets()` | 3개 파일에 중복 | `config.guess_target()` / `config.guess_targets()` |

**효과**
- 설정 변경 시 `config.py` 또는 환경변수만 수정
- 중복 코드 약 80줄 제거
- 새 시스템 추가 시 `monitoring.json`만 수정하면 자동 반영

---

### 2.6 Context 관리 (대화 요약)

**문제점**  
`session_store.py`가 대화를 무한정 쌓기만 하고, LLM에 넘길 때 `history[-10:]`으로 단순히 잘라 사용하고 있었다. 10턴 이전의 맥락은 완전히 소실되었다.

**개선 내용**  
대화가 10턴(SUMMARIZE_THRESHOLD) 이상 쌓이면 fast LLM으로 오래된 턴을 요약하여 SQLite에 저장하고, 이후에는 `[이전 대화 요약] + 최근 4턴`만 LLM에 전달하도록 변경하였다.

```
변경 전: history[-10:] → 10턴 이전 맥락 소실

변경 후:
  10턴 미만 → 전체 이력 그대로
  10턴 이상 → fast_llm.summarize(오래된 턴)
              → SQLite summaries 테이블에 저장
              → [이전 대화 요약] + 최근 4턴만 LLM에 전달
```

**변경 파일**

| 파일 | 변경 |
|---|---|
| `agent/session_store.py` | `summaries` 테이블, `load_with_summary()`, `needs_summarization()`, `save_summary()` 추가 |
| `agent/fake_llm.py` | `FastLLM.summarize()` 추가 |
| `agent/ollama_llm.py` | `OllamaFastLLM.summarize()` 추가 |
| `agent/openai_llm.py` | `OpenAIFastLLM.summarize()` 추가 |
| `server.py` | `load()` → `load_with_summary()`, 응답 후 `_maybe_summarize()` 호출 |

**효과**
- 10턴 이전 맥락도 요약으로 보존
- LLM에 전달하는 토큰 수 감소 (전체 이력 → 요약 + 최근 4턴)
- 요약은 fast LLM(저비용 모델)이 담당하여 추가 비용 최소화

---

## 3. 변경 후 프로젝트 구조

```
all_total_vue_student/
├── server.py
├── mcp_server.py
├── mcp_server_docs.py
├── web_chat.html
├── web_demo_server.py
├── requirements.txt
│
├── agent/
│   ├── config.py              ← [신규] 설정 중앙 관리
│   ├── state.py               ← [신규] AgentState 타입 정의
│   ├── rag.py                 ← [신규] ChromaDB 기반 런북 RAG
│   ├── graph.py               ← [수정] 62줄로 축소 (조립만)
│   ├── deps.py
│   ├── supervisor_v1.py       ← [수정] config 사용
│   ├── fake_llm.py            ← [수정] summarize 추가
│   ├── ollama_llm.py          ← [수정] config 사용 + summarize 추가
│   ├── openai_llm.py          ← [수정] config 사용 + summarize 추가
│   ├── mcp_client.py
│   ├── retry.py
│   ├── session_store.py       ← [수정] 요약 관리 추가
│   │
│   ├── nodes/                 ← [신규] 노드 모듈
│   │   ├── __init__.py
│   │   ├── route.py
│   │   ├── plan.py
│   │   ├── gate.py
│   │   ├── research.py
│   │   ├── analysis.py
│   │   └── write.py
│   │
│   └── agents/                ← [신규] 서브 에이전트
│       ├── __init__.py
│       ├── monitor_agent.py
│       └── runbook_agent.py
│
├── eval/                      ← [신규] 평가 프레임워크
│   ├── __init__.py
│   ├── test_cases.py
│   ├── judge.py
│   └── run_eval.py
│
├── data/
│   ├── monitoring.json
│   ├── chroma_db/             ← [신규] 벡터DB 저장소
│   └── runbooks/
│
├── sh/
│   ├── index_runbooks.sh      ← [신규] RAG 인덱싱 스크립트
│   └── (기존 스크립트들)
│
└── doc/
    └── improvement_report.md  ← 이 문서
```

---

## 4. 실행 절차 (개선 후)

```bash
# 1. 가상환경 준비
bash sh/setup_venv.sh

# 2. Ollama 환경 준비
bash sh/setup_ollama.sh

# 3. 런북 RAG 인덱싱 (최초 1회)
bash sh/index_runbooks.sh

# 4. .env 설정
cp .env.example .env
# LANGCHAIN_API_KEY 등 편집

# 5. 에이전트 기동
bash sh/run_agent_ollma.sh

# 6. (선택) 평가 실행
cd eval
python run_eval.py --judge
```

---

## 5. 향후 개선 가능 항목

| # | 영역 | 내용 |
|---|---|---|
| 1 | 데이터 보강 | incident_type 추가, 런북 문서 확장, monitoring.json 시나리오 다양화 |
| 2 | 평가 고도화 | 테스트 케이스 추가, 자동 회귀 테스트 CI 연동 |
| 3 | 프론트엔드 | RAG 검색 결과 시각화, 요약 이력 표시 |
