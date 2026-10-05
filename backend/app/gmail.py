"""Gmail access: OAuth (read-only scope) and fetching recent messages."""

import base64
import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from .config import Settings
from .models import Email

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class GmailAuth:
    """Runs the OAuth web flow and keeps the user's token on disk."""

    def __init__(self, settings: Settings):
        self.settings = settings
        # state -> PKCE code verifier, held between /auth/login and /auth/callback
        self._pending: dict[str, str | None] = {}
        if settings.google_redirect_uri.startswith("http://localhost"):
            # oauthlib refuses plain http unless told this is local development.
            os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

    def _flow(self, state: str | None = None) -> Flow:
        return Flow.from_client_secrets_file(
            str(self.settings.google_client_secrets_file),
            scopes=SCOPES,
            state=state,
            redirect_uri=self.settings.google_redirect_uri,
        )

    def authorization_url(self) -> str:
        flow = self._flow()
        url, state = flow.authorization_url(access_type="offline", prompt="consent")
        self._pending[state] = flow.code_verifier
        return url

    def handle_callback(self, authorization_response: str, state: str) -> None:
        if state not in self._pending:
            raise ValueError("Unknown or expired OAuth state")
        flow = self._flow(state=state)
        flow.code_verifier = self._pending.pop(state)
        flow.fetch_token(authorization_response=authorization_response)
        self._save(flow.credentials)

    def credentials(self) -> Credentials | None:
        path: Path = self.settings.token_path
        if not path.exists():
            return None
        creds = Credentials.from_authorized_user_file(str(path), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self._save(creds)
        return creds if creds.valid else None

    def disconnect(self) -> None:
        self.settings.token_path.unlink(missing_ok=True)

    def _save(self, creds: Credentials) -> None:
        self.settings.token_path.write_text(creds.to_json())


class GmailClient:
    def __init__(self, creds: Credentials):
        self.service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    def list_message_ids(self, query: str, limit: int) -> list[str]:
        resp = self.service.users().messages().list(userId="me", q=query, maxResults=limit).execute()
        return [m["id"] for m in resp.get("messages", [])]

    def get_email(self, message_id: str) -> Email:
        msg = self.service.users().messages().get(userId="me", id=message_id, format="full").execute()
        return parse_message(msg)


def parse_message(msg: dict) -> Email:
    payload = msg.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}

    received_at = datetime.fromtimestamp(int(msg.get("internalDate", "0")) / 1000, tz=timezone.utc)
    if "date" in headers:
        try:
            received_at = parsedate_to_datetime(headers["date"])
        except (TypeError, ValueError):
            pass

    return Email(
        id=msg["id"],
        thread_id=msg.get("threadId", msg["id"]),
        sender=headers.get("from", ""),
        subject=headers.get("subject", "(no subject)"),
        received_at=received_at,
        snippet=msg.get("snippet", ""),
        body=_extract_body(payload),
    )


def _extract_body(payload: dict) -> str:
    """Prefer text/plain; fall back to text/html stripped of tags."""
    plain = _find_part(payload, "text/plain")
    if plain:
        return plain
    html = _find_part(payload, "text/html")
    return _strip_html(html) if html else ""


def _find_part(part: dict, mime_type: str) -> str | None:
    if part.get("mimeType") == mime_type and part.get("body", {}).get("data"):
        return _decode(part["body"]["data"])
    for sub in part.get("parts", []) or []:
        found = _find_part(sub, mime_type)
        if found:
            return found
    return None


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.chunks: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.chunks.append(data.strip())


def _strip_html(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return "\n".join(parser.chunks)
