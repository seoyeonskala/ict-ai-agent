"""세션 저장소 — SQLite 기반 대화 이력 + 요약 관리.

대화가 길어지면(SUMMARIZE_THRESHOLD 이상) 오래된 턴을 LLM으로 요약해
토큰 비용과 컨텍스트 크기를 줄인다.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "session.db"

SUMMARIZE_THRESHOLD = 10
KEEP_RECENT = 4


class SqliteSessionStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS messages ("
            " thread_id TEXT, role TEXT, content TEXT, created TEXT)"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS summaries ("
            " thread_id TEXT PRIMARY KEY, summary TEXT, turn_count INTEGER,"
            " updated TEXT)"
        )
        self.conn.commit()

    def load(self, thread_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT role, content FROM messages WHERE thread_id=? ORDER BY rowid",
            (thread_id,),
        ).fetchall()
        return [{"role": r, "content": c} for r, c in rows]

    def load_with_summary(self, thread_id: str) -> list[dict]:
        """요약이 있으면 요약 + 최근 턴만 반환, 없으면 전체 반환."""
        summary = self._get_summary(thread_id)
        all_msgs = self.load(thread_id)
        if summary and len(all_msgs) > KEEP_RECENT:
            recent = all_msgs[-KEEP_RECENT:]
            return [{"role": "system", "content": f"[이전 대화 요약] {summary}"}] + recent
        return all_msgs

    def append(self, thread_id: str, role: str, content: str) -> None:
        self.conn.execute(
            "INSERT INTO messages VALUES (?,?,?,?)",
            (thread_id, role, content, datetime.now().isoformat()),
        )
        self.conn.commit()

    def needs_summarization(self, thread_id: str) -> bool:
        count = self.conn.execute(
            "SELECT COUNT(*) FROM messages WHERE thread_id=?", (thread_id,)
        ).fetchone()[0]
        return count >= SUMMARIZE_THRESHOLD

    def get_older_messages(self, thread_id: str) -> list[dict]:
        """요약 대상인 오래된 메시지들을 반환 (최근 KEEP_RECENT개 제외)."""
        all_msgs = self.load(thread_id)
        if len(all_msgs) <= KEEP_RECENT:
            return []
        return all_msgs[:-KEEP_RECENT]

    def save_summary(self, thread_id: str, summary: str, turn_count: int) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO summaries VALUES (?,?,?,?)",
            (thread_id, summary, turn_count, datetime.now().isoformat()),
        )
        self.conn.commit()

    def _get_summary(self, thread_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT summary FROM summaries WHERE thread_id=?", (thread_id,)
        ).fetchone()
        return row[0] if row else None

    def close(self) -> None:
        self.conn.close()
