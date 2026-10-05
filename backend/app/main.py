import logging

import anthropic
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from .config import Settings, get_settings
from .extractor import Extractor
from .gmail import GmailAuth, GmailClient
from .models import SyncResult, Task, TaskUpdate
from .store import Store

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

settings = get_settings()
app = FastAPI(title="Email Tracker")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_methods=["*"],
    allow_headers=["*"],
)

_auth = GmailAuth(settings)
_store = Store(settings.db_path)


def get_store() -> Store:
    return _store


def get_auth() -> GmailAuth:
    return _auth


def get_extractor(s: Settings = Depends(get_settings)) -> Extractor:
    if not s.anthropic_api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY is not set")
    return Extractor(anthropic.Anthropic(api_key=s.anthropic_api_key), s.claude_model, s.claude_effort)


def get_gmail(auth: GmailAuth = Depends(get_auth)) -> GmailClient:
    creds = auth.credentials()
    if creds is None:
        raise HTTPException(401, "Gmail is not connected")
    return GmailClient(creds)


@app.get("/health")
def health():
    return {"ok": True}


# --- Gmail auth -------------------------------------------------------------


@app.get("/auth/status")
def auth_status(auth: GmailAuth = Depends(get_auth)):
    return {"connected": auth.credentials() is not None}


@app.get("/auth/login")
def auth_login(auth: GmailAuth = Depends(get_auth)):
    return RedirectResponse(auth.authorization_url())


@app.get("/auth/callback")
def auth_callback(request: Request, state: str, auth: GmailAuth = Depends(get_auth)):
    try:
        auth.handle_callback(str(request.url), state)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(settings.frontend_url)


@app.post("/auth/logout")
def auth_logout(auth: GmailAuth = Depends(get_auth)):
    auth.disconnect()
    return {"connected": False}


# --- Sync and tasks -------------------------------------------------------------


@app.post("/sync", response_model=SyncResult)
def sync(
    gmail: GmailClient = Depends(get_gmail),
    extractor: Extractor = Depends(get_extractor),
    store: Store = Depends(get_store),
    s: Settings = Depends(get_settings),
):
    """Pull recent emails, extract action points from new ones, and file them into quadrants."""
    scanned = skipped = created = 0
    for message_id in gmail.list_message_ids(s.gmail_query, s.max_emails_per_sync):
        if store.is_processed(message_id):
            skipped += 1
            continue
        email = gmail.get_email(message_id)
        actions = extractor.extract(email)
        created += store.save_extraction(email, actions)
        scanned += 1
    log.info("Sync done: %d scanned, %d skipped, %d tasks", scanned, skipped, created)
    return SyncResult(emails_scanned=scanned, emails_skipped=skipped, tasks_created=created)


@app.get("/tasks", response_model=list[Task])
def list_tasks(include_done: bool = False, store: Store = Depends(get_store)):
    return store.list_tasks(include_done=include_done)


@app.patch("/tasks/{task_id}", response_model=Task)
def update_task(task_id: int, update: TaskUpdate, store: Store = Depends(get_store)):
    task = store.update_task(task_id, update)
    if task is None:
        raise HTTPException(404, "Task not found")
    return task


@app.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, store: Store = Depends(get_store)):
    if not store.delete_task(task_id):
        raise HTTPException(404, "Task not found")
