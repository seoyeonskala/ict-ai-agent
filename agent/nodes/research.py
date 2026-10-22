"""research 노드 — MonitorAgent / RunbookAgent에 태스크를 분배하고 결과를 합친다."""
import asyncio
import time

from langsmith import traceable

from ..agents import MonitorAgent, RunbookAgent
from ..deps import SupervisorDeps
from ..state import AgentState


@traceable(name="research_node")
async def research_node(state: AgentState, deps: SupervisorDeps) -> dict:
    tasks = state["tasks"]
    has_pending = any(t["agent"] == "research" and t["status"] == "pending"
                      for t in tasks)
    if not has_pending:
        return {"events": state["events"] +
                [{"type": "ResearchSkipped", "reason": "pending research task 0개"}]}

    monitor = MonitorAgent(deps)
    runbook = RunbookAgent(state["query"])

    started = time.perf_counter()
    monitor_results, runbook_results = await asyncio.gather(
        monitor.run(tasks), runbook.run(tasks))
    elapsed = round(time.perf_counter() - started, 2)

    all_results = monitor_results + runbook_results
    new_tasks = [dict(t) for t in tasks]
    collected = list(state.get("collected", []))
    events = list(state["events"])
    retry_total = state.get("retry_count", 0)

    for r in all_results:
        new_tasks[r["idx"]]["status"] = "done"
        collected.append({"source": r["source"], "data": r["data"]})
        retry_total += r["retries"]
        events.append({"type": "TaskCompleted", "id": r["task_id"],
                       "source": r["source"], "target": r["target"],
                       "retries": r["retries"]})

    return {"tasks": new_tasks, "collected": collected, "retry_count": retry_total,
            "parallel_elapsed": elapsed, "events": events}


@traceable(name="replan_check_node")
async def replan_check_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """수집 결과 평가 — RAG 검색 결과가 있으면 충분, 없으면 재조사."""
    has_runbook = any(
        c["source"] == "runbook" and c["data"].get("chunks")
        for c in state.get("collected", []))
    rounds = state.get("replan_rounds", 0)
    if has_runbook or rounds >= 1:
        verdict = {"type": "ReplanCheck", "round": rounds, "is_sufficient": True}
        return {"events": state["events"] + [verdict]}
    gap_task = {"id": "task-gap-runbook", "agent": "research", "kind": "runbook",
                "target": state["query"], "status": "pending"}
    verdict = {"type": "ReplanCheck", "round": rounds, "is_sufficient": False,
               "gap_task": gap_task["id"]}
    return {"tasks": state["tasks"] + [gap_task], "replan_rounds": rounds + 1,
            "events": state["events"] + [verdict]}
