"""평가용 테스트 케이스 — 쿼리 + 기대 키워드 + LLM-as-judge 기준."""

TEST_CASES = [
    {
        "id": "tc-1",
        "query": "auth-service 로그인 응답이 느려졌어요. 원인 확인해주세요",
        "expected_route": "incident",
        "keywords": ["auth-service", "CPU", "1)"],
        "judge_criteria": "응답이 수집된 모니터링 수치(CPU%, 메모리%, 상태)를 정확히 인용하고 있는가",
    },
    {
        "id": "tc-2",
        "query": "web-01 CPU 급증 원인 진단해줘",
        "expected_route": "incident",
        "keywords": ["web-01", "CPU", "1)"],
        "judge_criteria": "응답이 수집된 모니터링 수치를 정확히 인용하고, CPU 급증에 대한 구체적 대응 절차를 포함하는가",
    },
    {
        "id": "tc-3",
        "query": "payments-service 결제 응답이 느려지고 CPU가 치솟았어요",
        "expected_route": "incident",
        "keywords": ["payments-service", "CPU", "1)"],
        "judge_criteria": "응답이 payments-service의 수집된 수치를 인용하고, 대응 절차가 번호 형식으로 제시되는가",
    },
    {
        "id": "tc-4",
        "query": "cache-service 메모리 사용률이 계속 올라가고 있어요",
        "expected_route": "incident",
        "keywords": ["cache-service", "메모리", "1)"],
        "judge_criteria": "응답이 cache-service의 메모리 수치를 정확히 인용하고, 메모리 누수 대응 절차를 포함하는가",
    },
    {
        "id": "tc-5",
        "query": "안녕, 너는 누구야?",
        "expected_route": "chat",
        "keywords": [],
        "judge_criteria": "일상 대화에 적절히 응답하고, 불필요한 장애 진단을 수행하지 않았는가",
    },
]
