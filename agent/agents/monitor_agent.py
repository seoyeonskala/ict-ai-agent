"""모니터링 전담 에이전트 — MCP Tool로 시스템 상태를 조회한다."""
import asyncio

from langsmith import traceable

from ..config import MCP_TOOL_MONITORING
from ..deps import SupervisorDeps
from ..retry import with_retry


class MonitorAgent:
    def __init__(self, deps: SupervisorDeps):
        self.deps = deps

    @traceable(name="monitor_agent")
    async def run(self, tasks: list[dict]) -> list[dict]:
        """pending 상태인 monitoring 태스크를 병렬 실행하고 결과를 반환."""
        pending = [(i, t) for i, t in enumerate(tasks)
                   if t["agent"] == "research" and t["kind"] == "monitoring"
                   and t["status"] == "pending"]
        if not pending:
            return []

        async def _run_one(idx: int, task: dict) -> dict:
            await asyncio.sleep(0.35)
            data, retries = await with_retry(
                self.deps.mcp.call_tool, MCP_TOOL_MONITORING,
                {"system_name": task["target"]})
            return {"idx": idx, "source": "monitoring", "data": data,
                    "retries": retries, "target": task["target"],
                    "task_id": task["id"]}

        results = await asyncio.gather(*(_run_one(i, t) for i, t in pending))
        return list(results)
