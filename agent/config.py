"""에이전트 설정 — 하드코딩 값을 한 곳에서 관리."""
import json
import os
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Ollama
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")

# MCP 이름
MCP_PROMPT_NAME = "incident_analysis_prompt"
MCP_TOOL_MONITORING = "get_monitoring_status"
MCP_RESOURCE_RUNBOOK = "get_incident_runbook"

# 디폴트 시스템
DEFAULT_SYSTEM = os.environ.get("DEFAULT_SYSTEM", "auth-service")


def load_known_systems() -> set[str]:
    """data/monitoring.json에서 시스템 목록을 읽는다."""
    path = DATA_DIR / "monitoring.json"
    try:
        return set(json.loads(path.read_text()).keys())
    except (OSError, json.JSONDecodeError):
        return {DEFAULT_SYSTEM}


KNOWN_SYSTEMS = load_known_systems()


def guess_target(query: str) -> str:
    """쿼리에서 KNOWN_SYSTEMS에 매칭되는 첫 번째 시스템을 찾는다."""
    matches = [(query.index(s), s) for s in KNOWN_SYSTEMS if s in query]
    return min(matches)[1] if matches else DEFAULT_SYSTEM


def guess_targets(query: str) -> list[str]:
    """쿼리에 등장하는 KNOWN_SYSTEMS 전부를 반환한다."""
    matched = sorted(s for s in KNOWN_SYSTEMS if s in query)
    return matched or [DEFAULT_SYSTEM]
