"""SQLite persistence for processed emails and extracted tasks."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .models import Email, ExtractedAction, Quadrant, Task, TaskUpdate

SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_emails (
    id TEXT PRIMARY KEY,
    processed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id TEXT NOT NULL,
    email_subject TEXT NOT NULL,
    email_sender TEXT NOT NULL,
    title TEXT NOT NULL,
    details TEXT NOT NULL,
    due_date TEXT,
    quadrant TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: Path | str):
        self.path = str(path)
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def is_processed(self, email_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute("SELECT 1 FROM processed_emails WHERE id = ?", (email_id,)).fetchone()
        return row is not None

    def save_extraction(self, email: Email, actions: list[ExtractedAction]) -> int:
        """Record an email as processed along with its action points. Returns tasks created."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute("INSERT OR IGNORE INTO processed_emails (id, processed_at) VALUES (?, ?)", (email.id, now))
            for action in actions:
                conn.execute(
                    """INSERT INTO tasks (email_id, email_subject, email_sender, title, details,
                                          due_date, quadrant, reasoning, done, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
                    (
                        email.id,
                        email.subject,
                        email.sender,
                        action.title,
                        action.details,
                        action.due_date,
                        Quadrant.from_flags(action.urgent, action.important).value,
                        action.reasoning,
                        now,
                    ),
                )
        return len(actions)

    def list_tasks(self, include_done: bool = False) -> list[Task]:
        query = "SELECT * FROM tasks"
        if not include_done:
            query += " WHERE done = 0"
        query += " ORDER BY due_date IS NULL, due_date, created_at DESC"
        with self._conn() as conn:
            rows = conn.execute(query).fetchall()
        return [self._row_to_task(r) for r in rows]

    def update_task(self, task_id: int, update: TaskUpdate) -> Task | None:
        fields, values = [], []
        if update.quadrant is not None:
            fields.append("quadrant = ?")
            values.append(update.quadrant.value)
        if update.done is not None:
            fields.append("done = ?")
            values.append(int(update.done))
        with self._conn() as conn:
            if fields:
                conn.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", (*values, task_id))
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return self._row_to_task(row) if row else None

    def delete_task(self, task_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return cur.rowcount > 0

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> Task:
        return Task(
            id=row["id"],
            email_id=row["email_id"],
            email_subject=row["email_subject"],
            email_sender=row["email_sender"],
            title=row["title"],
            details=row["details"],
            due_date=row["due_date"],
            quadrant=Quadrant(row["quadrant"]),
            reasoning=row["reasoning"],
            done=bool(row["done"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
