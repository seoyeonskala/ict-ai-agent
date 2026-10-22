"""평가 실행기 — 에이전트 서버에 테스트 쿼리를 보내고 키워드 매칭 + LLM-as-judge로 채점.

사용법:
  # 에이전트 서버가 떠 있는 상태에서
  python eval/run_eval.py                          # 키워드 매칭만
  python eval/run_eval.py --judge                  # 키워드 + LLM-as-judge (ollama)
  python eval/run_eval.py --judge --backend openai # 키워드 + LLM-as-judge (openai)
"""
import argparse
import json
import sys
import time

import httpx

from test_cases import TEST_CASES
from judge import judge

SERVER_URL = "http://127.0.0.1:8100"


def _keyword_score(response: str, keywords: list[str]) -> dict:
    if not keywords:
        return {"score": 1.0, "matched": [], "missed": []}
    matched = [k for k in keywords if k in response]
    missed = [k for k in keywords if k not in response]
    return {"score": round(len(matched) / len(keywords), 2),
            "matched": matched, "missed": missed}


def run_eval(use_judge: bool = False, backend: str = "ollama"):
    results = []
    total_keyword = 0.0
    total_judge = 0.0
    judge_count = 0

    for tc in TEST_CASES:
        print(f"\n{'='*60}")
        print(f"[{tc['id']}] {tc['query']}")
        print(f"{'='*60}")

        try:
            start = time.time()
            resp = httpx.post(f"{SERVER_URL}/chat",
                              json={"message": tc["query"],
                                    "thread_id": f"eval-{tc['id']}"},
                              timeout=300.0)
            elapsed = round(time.time() - start, 2)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"id": tc["id"], "error": str(e)})
            continue

        reply = data["reply"]
        route = data.get("metadata", {}).get("route", "?")
        print(f"  route: {route} (기대: {tc['expected_route']})")
        print(f"  응답: {reply[:120]}...")
        print(f"  소요: {elapsed}s")

        # 1) 라우트 일치 여부
        route_ok = route == tc["expected_route"]
        print(f"  라우트 일치: {'O' if route_ok else 'X'}")

        # 2) 키워드 매칭
        kw = _keyword_score(reply, tc["keywords"])
        total_keyword += kw["score"]
        print(f"  키워드 점수: {kw['score']} (매칭: {kw['matched']}, 누락: {kw['missed']})")

        # 3) LLM-as-judge
        judge_result = None
        if use_judge and tc["judge_criteria"]:
            print(f"  LLM-as-judge 채점 중 ({backend})...")
            judge_result = judge(tc["query"], reply, tc["judge_criteria"],
                                backend=backend)
            total_judge += judge_result.get("score", 0)
            judge_count += 1
            print(f"  LLM 점수: {judge_result['score']}/5 — {judge_result['reason']}")

        results.append({
            "id": tc["id"],
            "query": tc["query"],
            "route": route,
            "route_ok": route_ok,
            "keyword_score": kw["score"],
            "keyword_detail": kw,
            "judge_score": judge_result.get("score") if judge_result else None,
            "judge_reason": judge_result.get("reason") if judge_result else None,
            "elapsed": elapsed,
        })

    # 요약
    n = len(TEST_CASES)
    print(f"\n{'='*60}")
    print(f"평가 요약 ({n}건)")
    print(f"{'='*60}")
    print(f"  키워드 매칭 평균: {round(total_keyword / n, 2)}")
    if judge_count:
        print(f"  LLM-as-judge 평균: {round(total_judge / judge_count, 1)}/5")
    route_ok_count = sum(1 for r in results if r.get("route_ok"))
    print(f"  라우트 정확도: {route_ok_count}/{n}")

    out_path = "eval/eval_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n결과 저장: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge", action="store_true", help="LLM-as-judge 평가 포함")
    parser.add_argument("--backend", default="ollama", choices=["ollama", "openai"],
                        help="judge LLM 백엔드 (기본: ollama)")
    args = parser.parse_args()
    run_eval(use_judge=args.judge, backend=args.backend)
