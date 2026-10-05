from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Quadrant(str, Enum):
    """Eisenhower matrix quadrants."""

    DO = "do"  # urgent + important
    SCHEDULE = "schedule"  # important, not urgent
    DELEGATE = "delegate"  # urgent, not important
    ELIMINATE = "eliminate"  # neither

    @classmethod
    def from_flags(cls, urgent: bool, important: bool) -> "Quadrant":
        if urgent and important:
            return cls.DO
        if important:
            return cls.SCHEDULE
        if urgent:
            return cls.DELEGATE
        return cls.ELIMINATE


class Email(BaseModel):
    id: str
    thread_id: str
    sender: str
    subject: str
    received_at: datetime
    snippet: str
    body: str


class ExtractedAction(BaseModel):
    """One action point as returned by Claude."""

    title: str = Field(description="Short imperative description of what to do")
    details: str = Field(description="One or two sentences of context from the email")
    due_date: str | None = Field(description="ISO date (YYYY-MM-DD) if the email states or implies a deadline, else null")
    urgent: bool = Field(description="True if it needs attention within ~48 hours or has a near deadline")
    important: bool = Field(description="True if it matters to the recipient's goals, work, money, health or relationships")
    reasoning: str = Field(description="One short sentence explaining the urgent/important call")


class ExtractionResult(BaseModel):
    actions: list[ExtractedAction]


class Task(BaseModel):
    id: int
    email_id: str
    email_subject: str
    email_sender: str
    title: str
    details: str
    due_date: str | None
    quadrant: Quadrant
    reasoning: str
    done: bool
    created_at: datetime


class TaskUpdate(BaseModel):
    quadrant: Quadrant | None = None
    done: bool | None = None


class SyncResult(BaseModel):
    emails_scanned: int
    emails_skipped: int
    tasks_created: int
