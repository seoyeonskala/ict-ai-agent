"""런북 전담 에이전트 — RAG 벡터 검색으로 관련 런북을 조회한다."""
import asyncio
from functools import partial

from langsmith import traceable

from ..rag import search_runbooks

SCORE_THRESHOLD = 0.3


class RunbookAgent:
    def __init__(self, query: str):
        self.query = query

    @traceable(name="runbook_agent")
    async def run(self, tasks: list[dict]) -> list[dict]:
        """pending 상태인 runbook 태스크를 RAG 검색으로 처리."""
        pending = [(i, t) for i, t in enumerate(tasks)
                   if t["agent"] == "research" and t["kind"] == "runbook"
                   and t["status"] == "pending"]
        if not pending:
            return []

        loop = asyncio.get_event_loop()
        hits = await loop.run_in_executor(
            None, partial(search_runbooks, self.query, n_results=5))
        chunks = [h["text"] for h in hits if h["score"] >= SCORE_THRESHOLD]
        sources = list({h["source"] for h in hits if h["score"] >= SCORE_THRESHOLD})

        results = []
        for idx, task in pending:
            results.append({
                "idx": idx, "source": "runbook",
                "data": {"chunks": chunks, "sources": sources},
                "retries": 0, "target": task["target"],
                "task_id": task["id"]})
        return results
