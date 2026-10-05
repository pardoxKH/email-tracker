"""Uses Claude to pull action points out of an email and judge urgency/importance."""

import logging
from datetime import date

import anthropic

from .models import Email, ExtractedAction, ExtractionResult

log = logging.getLogger(__name__)

# Long emails are rare but a quoted thread can be huge; the tail is almost always older quoted replies.
MAX_BODY_CHARS = 20_000

SYSTEM_PROMPT = """\
You read one email from the user's inbox and list the concrete action points it asks of the user.

An action point is something the user personally needs to do: reply, decide, pay, review, attend, \
send, sign, book, follow up. Newsletters, receipts, notifications and marketing usually have none; \
return an empty list for those rather than inventing work.

For each action point, judge it on the Eisenhower matrix:
- urgent: it needs attention within about 48 hours, or has a deadline that is close.
- important: it matters to the user's work, money, health, legal standing or relationships.

Keep titles short and imperative ("Reply to Sam about the Q3 budget"). Use the email's own dates \
for due_date, resolved against today's date, and leave it null when no deadline is stated or implied."""


class Extractor:
    def __init__(self, client: anthropic.Anthropic, model: str, effort: str = "low"):
        self.client = client
        self.model = model
        self.effort = effort

    def extract(self, email: Email, today: date | None = None) -> list[ExtractedAction]:
        today = today or date.today()
        body = email.body[:MAX_BODY_CHARS] if email.body else email.snippet
        content = (
            f"Today's date: {today.isoformat()}\n\n"
            f"<email>\nFrom: {email.sender}\nSubject: {email.subject}\n"
            f"Received: {email.received_at.isoformat()}\n\n{body}\n</email>"
        )

        response = self.client.messages.parse(
            model=self.model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
            output_config={"effort": self.effort},
            output_format=ExtractionResult,
        )

        if response.stop_reason == "refusal":
            log.warning("Claude declined email %s; skipping", email.id)
            return []
        if response.parsed_output is None:
            log.warning("No structured output for email %s (stop_reason=%s)", email.id, response.stop_reason)
            return []
        return response.parsed_output.actions
