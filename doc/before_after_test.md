# Before/After 실측 비교 테스트 가이드

## 사전 준비

### 1. Ollama 실행 확인
```bash
# Ollama가 떠있는지 확인
curl http://127.0.0.1:11434/api/tags

# 안 떠있으면 실행
ollama serve
```

### 2. 런북 인덱싱 (RAG용 — 최초 1회만)
```bash
cd /Users/seoyeon/Downloads/all_total_vue_student
python3 -c "from agent.rag import index_runbooks; print(f'{index_runbooks()}개 청크 인덱싱 완료')"
```
- 성공 시: `28개 청크 인덱싱 완료` 출력
- `data/chroma_db/` 폴더에 벡터 DB 생성됨

### 3. 서버 실행
```bash
# 터미널 1 — 백엔드 서버 (포트 8100)
cd /Users/seoyeon/Downloads/all_total_vue_student
LLM_BACKEND=ollama python3 server.py

# 터미널 2 — 웹 데모 서버 (포트 8600, 선택사항)
cd /Users/seoyeon/Downloads/all_total_vue_student
python3 web_demo_server.py
```

### 4. 서버 정상 확인
```bash
curl http://127.0.0.1:8100/health
```
응답 예시:
```json
{
  "status": "ok",
  "llm_backend": "ollama",
  "fast_llm": "ollama:qwen3:0.6b",
  "quality_llm": "ollama:qwen3:8b"
}
```

---

## 테스트 실행

### 테스트 1: incident 진단 (핵심 테스트)
```bash
curl -s "http://127.0.0.1:8100/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "auth-service 서버 장애 발생, CPU 급증하고 응답 지연됨. 긴급 진단 요청", "thread_id": "test-incident-1"}' \
  | python3 -m json.tool
```

#### 확인할 항목:
- `events`에 `RouteDecided → route: "incident"` 있는지
- `PlanCreated` 에 targets에 `auth-service` 포함되는지
- `TaskCompleted`에 `source: "monitoring"` (MCP Tool 호출)이 있는지
- `TaskCompleted`에 `source: "runbook"` (RAG 검색)이 있는지
- `ReplanCheck`에 `is_sufficient: true`가 나오는지
- `DraftWritten` → `Validation` → `verdict: "합격"` 흐름이 보이는지
- `reply`에 CPU %, 메모리 %, 알림 등 실측 수치가 인용되는지
- `metadata.cost_usd` 값 확인
- `metadata.parallel_elapsed` 값 확인 (병렬 실행 시간)

#### 실측 결과 예시 (2026-10-21 테스트):
```
route:              incident
task 수:            3 (monitoring + runbook + analysis)
replan 라운드:      1 (runbook 부족 감지 → 자동 보강)
병렬 실행 시간:     0.17초
검증 시도:          1회 (1차 합격)
총 비용 (가상):     $0.003844
응답 품질:          CPU 77%, 메모리 60.5%, connection pool 92% 등 수치 인용
```

### 테스트 2: chat 분류 확인
```bash
curl -s "http://127.0.0.1:8100/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "안녕하세요", "thread_id": "test-chat-1"}' \
  | python3 -m json.tool
```

#### 확인할 항목:
- `route: "chat"` 으로 분류되는지
- incident 파이프라인을 타지 않고 바로 응답하는지
- `cost_usd`가 incident보다 훨씬 낮은지

### 테스트 3: SSE 스트리밍 확인
```bash
curl -s "http://127.0.0.1:8100/chat/stream?message=payment-service%20장애%20진단&thread_id=test-stream-1"
```

#### 확인할 항목:
- `data: {...}` 형태로 이벤트가 하나씩 내려오는지
- 중간에 끊기지 않는지
- 마지막에 `data: [DONE]` 이 오는지

### 테스트 4: RAG 검색 단독 확인
```bash
python3 -c "
from agent.rag import search_runbooks
results = search_runbooks('auth-service CPU 급증 장애', n_results=5)
for r in results:
    print(f'[score={r[\"score\"]:.3f}] {r[\"source\"]} — {r[\"text\"][:80]}...')
"
```

#### 확인할 항목:
- 5건 이하의 결과가 유사도 점수와 함께 나오는지
- auth 관련 런북이 상위에 오는지

### 테스트 5: 대화 컨텍스트 유지 확인
```bash
# 첫 번째 메시지
curl -s "http://127.0.0.1:8100/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "내 이름은 김서연이야", "thread_id": "test-memory-1"}' \
  | python3 -m json.tool

# 두 번째 메시지 (같은 thread_id)
curl -s "http://127.0.0.1:8100/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "내 이름이 뭐라고 했지?", "thread_id": "test-memory-1"}' \
  | python3 -m json.tool
```

#### 확인할 항목:
- 두 번째 응답에서 "김서연"을 기억하고 답하는지

---

## Before/After 비교표 (발표용)

| 측정 항목 | Before (개선 전) | After (개선 후, 실측) |
|-----------|-----------------|----------------------|
| 런북 검색 방식 | MCP Resource 고정 1건 | RAG 벡터 검색 top-5 |
| research 구조 | 단일 노드 순차 | MonitorAgent + RunbookAgent 병렬 |
| 병렬 실행 시간 | 해당 없음 (순차) | 0.17초 |
| 자동 보강 | 없음 | replan으로 runbook 자동 추가 |
| graph.py | 339줄 단일 파일 | 62줄 + nodes/ 6개 모듈 |
| 컨텍스트 관리 | 전체 이력 전달 | 요약 + 최근 4턴 |
| 설정 관리 | 하드코딩 산재 | config.py 중앙화 |
| 평가 체계 | 없음 | LLM-as-judge + 키워드 채점 |
| 비용 추적 | 있음 | 있음 ($0.003844/건) |

## 참고: Before 수치 근거
- graph.py 339줄: 개선 전 원본 파일 기준 줄 수
- MCP Resource 고정 1건: 기존 `get_incident_runbook` 리소스는 시스템명 exact match로 1건만 반환
- 순차 실행: 기존 research_node는 for 루프로 task를 하나씩 처리
