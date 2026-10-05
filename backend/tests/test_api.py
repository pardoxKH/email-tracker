from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app, get_extractor, get_gmail, get_store
from app.models import Email, ExtractedAction
from app.store import Store


class FakeGmail:
    def __init__(self, ids):
        self.ids = ids

    def list_message_ids(self, query, limit):
        return self.ids[:limit]

    def get_email(self, message_id):
        return Email(
            id=message_id,
            thread_id=message_id,
            sender="boss@example.com",
            subject=f"Subject {message_id}",
            received_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
            snippet="",
            body="Please review the deck today.",
        )


class FakeExtractor:
    def extract(self, email):
        return [
            ExtractedAction(
                title=f"Review deck from {email.id}",
                details="",
                due_date=None,
                urgent=True,
                important=True,
                reasoning="due today",
            )
        ]


def test_sync_is_idempotent_and_tasks_can_be_updated(tmp_path):
    store = Store(tmp_path / "t.db")
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_gmail] = lambda: FakeGmail(["a", "b"])
    app.dependency_overrides[get_extractor] = lambda: FakeExtractor()
    try:
        client = TestClient(app)

        first = client.post("/sync").json()
        assert first == {"emails_scanned": 2, "emails_skipped": 0, "tasks_created": 2}
        second = client.post("/sync").json()
        assert second == {"emails_scanned": 0, "emails_skipped": 2, "tasks_created": 0}

        tasks = client.get("/tasks").json()
        assert len(tasks) == 2
        assert all(t["quadrant"] == "do" for t in tasks)

        task_id = tasks[0]["id"]
        resp = client.patch(f"/tasks/{task_id}", json={"quadrant": "delegate"})
        assert resp.status_code == 200 and resp.json()["quadrant"] == "delegate"

        assert client.patch(f"/tasks/{task_id}", json={"done": True}).status_code == 200
        assert len(client.get("/tasks").json()) == 1

        assert client.delete(f"/tasks/{task_id}").status_code == 204
        assert client.patch("/tasks/9999", json={"done": True}).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_sync_requires_gmail_connection(tmp_path):
    # No token on disk, so the real get_gmail dependency should reject the request.
    client = TestClient(app)
    assert client.post("/sync").status_code == 401
