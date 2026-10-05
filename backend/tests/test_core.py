import base64
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.extractor import Extractor
from app.gmail import parse_message
from app.models import Email, ExtractedAction, ExtractionResult, Quadrant, TaskUpdate
from app.store import Store


def make_email(id="m1", body="Please send the signed contract by Friday."):
    return Email(
        id=id,
        thread_id="t1",
        sender="Sam <sam@example.com>",
        subject="Contract",
        received_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
        snippet=body[:50],
        body=body,
    )


def action(title="Sign contract", urgent=True, important=True):
    return ExtractedAction(
        title=title, details="", due_date="2026-10-09", urgent=urgent, important=important, reasoning="deadline"
    )


@pytest.mark.parametrize(
    "urgent,important,expected",
    [
        (True, True, Quadrant.DO),
        (False, True, Quadrant.SCHEDULE),
        (True, False, Quadrant.DELEGATE),
        (False, False, Quadrant.ELIMINATE),
    ],
)
def test_quadrant_from_flags(urgent, important, expected):
    assert Quadrant.from_flags(urgent, important) == expected


def test_store_roundtrip(tmp_path):
    store = Store(tmp_path / "t.db")
    email = make_email()
    assert not store.is_processed(email.id)

    created = store.save_extraction(email, [action(), action("Read FYI", urgent=False, important=False)])
    assert created == 2
    assert store.is_processed(email.id)

    tasks = store.list_tasks()
    assert {t.quadrant for t in tasks} == {Quadrant.DO, Quadrant.ELIMINATE}

    first = tasks[0]
    moved = store.update_task(first.id, TaskUpdate(quadrant=Quadrant.SCHEDULE))
    assert moved.quadrant == Quadrant.SCHEDULE

    store.update_task(first.id, TaskUpdate(done=True))
    assert len(store.list_tasks()) == 1
    assert len(store.list_tasks(include_done=True)) == 2

    assert store.delete_task(first.id)
    assert not store.delete_task(first.id)


def test_email_with_no_actions_is_still_marked_processed(tmp_path):
    store = Store(tmp_path / "t.db")
    store.save_extraction(make_email("newsletter"), [])
    assert store.is_processed("newsletter")
    assert store.list_tasks() == []


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def test_extractor_returns_parsed_actions():
    parsed = ExtractionResult(actions=[action()])
    messages = FakeMessages(SimpleNamespace(stop_reason="end_turn", parsed_output=parsed))
    extractor = Extractor(SimpleNamespace(messages=messages), model="claude-opus-5-5")

    result = extractor.extract(make_email(), today=date(2026, 10, 5))

    assert [a.title for a in result] == ["Sign contract"]
    call = messages.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_format"] is ExtractionResult
    assert "2026-10-05" in call["messages"][0]["content"]
    assert "signed contract" in call["messages"][0]["content"]


def test_extractor_handles_refusal():
    messages = FakeMessages(SimpleNamespace(stop_reason="refusal", parsed_output=None))
    extractor = Extractor(SimpleNamespace(messages=messages), model="claude-opus-5-5")
    assert extractor.extract(make_email()) == []


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def test_parse_message_prefers_plain_text():
    msg = {
        "id": "abc",
        "threadId": "t",
        "snippet": "hi",
        "internalDate": "1759660800000",
        "payload": {
            "headers": [
                {"name": "From", "value": "Ana <ana@example.com>"},
                {"name": "Subject", "value": "Review"},
                {"name": "Date", "value": "Sun, 05 Oct 2026 10:00:00 +0000"},
            ],
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/html", "body": {"data": _b64("<p>HTML version</p>")}},
                {"mimeType": "text/plain", "body": {"data": _b64("Plain version")}},
            ],
        },
    }
    email = parse_message(msg)
    assert email.subject == "Review"
    assert email.sender == "Ana <ana@example.com>"
    assert email.body == "Plain version"
    assert email.received_at.hour == 10


def test_parse_message_strips_html_when_no_plain_text():
    msg = {
        "id": "abc",
        "payload": {
            "headers": [],
            "mimeType": "text/html",
            "body": {"data": _b64("<style>p{}</style><p>Pay the invoice</p><p>by Monday</p>")},
        },
    }
    email = parse_message(msg)
    assert email.body == "Pay the invoice\nby Monday"
    assert email.subject == "(no subject)"
