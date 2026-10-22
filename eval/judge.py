"""LLM-as-judge — 응답 품질을 LLM이 채점한다.

backend="ollama"(기본) 또는 "openai"로 전환 가능.
"""
import json
import os

import httpx

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 1, "maximum": 5},
        "reason": {"type": "string"},
    },
    "required": ["score", "reason"],
}

SYSTEM_PROMPT = (
    "당신은 ICT 운영 AI 에이전트의 응답 품질을 평가하는 심사관이다.\n"
    "아래 기준에 따라 1~5점으로 채점하고, 이유를 한두 문장으로 설명하라.\n\n"
    "- 5점: 수집된 수치를 정확히 인용하고, 절차가 구체적이며, 빠짐없이 답변함\n"
    "- 4점: 대부분 정확하나 일부 수치 누락 또는 절차가 약간 부족\n"
    "- 3점: 방향은 맞으나 수치 인용이 부정확하거나 절차가 모호\n"
    "- 2점: 관련 내용이 있으나 핵심을 놓치거나 부정확한 정보 포함\n"
    "- 1점: 질문과 무관하거나 완전히 부정확한 답변"
)


def _judge_ollama(query: str, response: str, criteria: str,
                  model: str = "qwen3:8b") -> dict:
    user = (f"## 평가 기준\n{criteria}\n\n"
            f"## 사용자 질문\n{query}\n\n"
            f"## 에이전트 응답\n{response}")
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": user}],
        "stream": False,
        "format": JUDGE_SCHEMA,
        "options": {"temperature": 0.0},
    }
    url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
    resp = httpx.post(url, json=payload, timeout=300.0)
    resp.raise_for_status()
    content = resp.json()["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"score": 0, "reason": f"JSON 파싱 실패: {content[:100]}"}


def _judge_openai(query: str, response: str, criteria: str,
                  model: str = "gpt-4o") -> dict:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"score": 0, "reason": "OPENAI_API_KEY 미설정"}
    user = (f"## 평가 기준\n{criteria}\n\n"
            f"## 사용자 질문\n{query}\n\n"
            f"## 에이전트 응답\n{response}")
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": user}],
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }
    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload, timeout=120.0)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"score": 0, "reason": f"JSON 파싱 실패: {content[:100]}"}


def judge(query: str, response: str, criteria: str,
          backend: str = "ollama", **kwargs) -> dict:
    """응답을 LLM이 채점. backend="ollama" 또는 "openai"."""
    if backend == "openai":
        return _judge_openai(query, response, criteria, **kwargs)
    return _judge_ollama(query, response, criteria, **kwargs)
