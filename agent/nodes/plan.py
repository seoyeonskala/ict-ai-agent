from langsmith import traceable

from ..config import MCP_PROMPT_NAME, guess_target
from ..deps import SupervisorDeps
from ..state import AgentState, add_cost


@traceable(name="plan_node")
async def plan_node(state: AgentState, deps: SupervisorDeps) -> dict:
    prompt_server = await deps.mcp.find_prompt(MCP_PROMPT_NAME)
    procedure = await deps.mcp.get_prompt(
        MCP_PROMPT_NAME,
        {"system_name": guess_target(state["query"]), "symptom": state["query"]},
        server=prompt_server,
    )
    result, usage = deps.fast_llm.plan(state["query"], procedure)
    targets = [t["target"] for t in result["tasks"]
               if t["agent"] == "research" and t.get("target")]
    event = {"type": "PlanCreated", "task_count": len(result["tasks"]),
             "targets": targets}
    return {"tasks": result["tasks"], "needs_analysis": result["needs_analysis"],
            "cost_usd": add_cost(state, usage), "events": state["events"] + [event]}
