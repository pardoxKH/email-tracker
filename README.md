# Email Tracker

Reads your recent Gmail, uses Claude to pull out the action points each email asks of you, and sorts them onto an Eisenhower matrix:

| | Urgent | Not urgent |
|---|---|---|
| **Important** | Do first | Schedule |
| **Not important** | Delegate | Eliminate |

From the board you can tick tasks off or drag them into a different quadrant when you disagree with Claude's call (hover a task to see its reasoning).

## How it works

- `backend/` is a FastAPI app (Python 3.11+).
  - `gmail.py` connects to Gmail with the read-only scope and fetches messages matching `GMAIL_QUERY` (default: inbox, last 7 days).
  - `extractor.py` sends each new email to Claude and gets back structured action points with `urgent` / `important` flags.
  - `store.py` keeps tasks and the list of already-processed emails in SQLite under `backend/data/`, so each email is only read once.
- `frontend/` is a Next.js app that shows the four quadrants and talks to the backend.

Nothing is sent or changed in your mailbox; the app only reads.

## Setup

### 1. Google OAuth client (one time)

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project (or pick one).
2. **APIs & Services → Library**: enable the **Gmail API**.
3. **APIs & Services → OAuth consent screen**: choose *External*, fill in the app name and your email, and add yourself under **Test users**. Leaving the app in *Testing* mode is fine for personal use.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID**:
   - Application type: **Web application**
   - Authorized redirect URI: `http://localhost:8000/auth/callback`
5. Download the JSON and save it as `backend/credentials.json`.

### 2. Anthropic API key

Create one at [console.anthropic.com](https://console.anthropic.com/) and put it in `backend/.env` (next step).

### 3. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then set ANTHROPIC_API_KEY
uvicorn app.main:app --reload --port 8000
```

### 4. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Open http://localhost:3000, click **Connect Gmail**, approve access, then click **Sync inbox**.

## Configuration

Set these in `backend/.env`:

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | (required) | Claude API key |
| `CLAUDE_MODEL` | `claude-sonnet-5-5` | Model used for extraction |
| `CLAUDE_EFFORT` | `low` | How much Claude thinks per email (`low`, `medium`, `high`) |
| `GMAIL_QUERY` | `in:inbox newer_than:7d` | Any Gmail search query |
| `MAX_EMAILS_PER_SYNC` | `25` | Cap on emails fetched per sync |
| `GOOGLE_CLIENT_SECRETS_FILE` | `credentials.json` | OAuth client file |
| `GOOGLE_REDIRECT_URI` | `http://localhost:8000/auth/callback` | Must match the OAuth client |
| `FRONTEND_URL` | `http://localhost:3000` | Where to send you after sign-in; also the allowed CORS origin |

## Tests

```bash
cd backend && pytest
cd frontend && npm run typecheck
```

The backend tests use fakes for Gmail and Claude, so they need no credentials.

## API

| Method | Path | |
|---|---|---|
| GET | `/auth/status` | Is Gmail connected |
| GET | `/auth/login` | Start Google sign-in |
| POST | `/auth/logout` | Forget the stored Gmail token |
| POST | `/sync` | Read new emails and extract tasks |
| GET | `/tasks?include_done=false` | List tasks |
| PATCH | `/tasks/{id}` | Body `{"quadrant": "schedule"}` and/or `{"done": true}` |
| DELETE | `/tasks/{id}` | Remove a task |
