# AutoApply — Project Guide for Claude

## What this project does

AutoApply automates job hunting. A user uploads a resume PDF via a single API call. The system parses the resume, discovers matching jobs, scores and filters them through a three-stage AI loop, finds recruiter emails, sends personalized outreach, and emails an XLSX report — all without manual intervention.

---

## Architecture overview

```
HTTP POST /start
    │
    ▼
FastAPI (app/main.py)
    │  saves PDF bytes, enqueues ARQ job
    ▼
Redis queue
    │
    ▼
ARQ Worker (app/workers/tasks.py)  ← run_pipeline()
    │
    ├─ 1. Parse resume PDF → structured profile  (app/parsers/resume.py)
    │
    ├─ 2. Loop: Generator → Evaluator → Verifier  (app/agents/loop.py)
    │       ├─ Generator: Adzuna API pages         (app/agents/generator.py)
    │       ├─ Evaluator: Claude Haiku scorer      (app/agents/evaluator.py)
    │       └─ Verifier:  Claude Haiku adversary   (app/agents/verifier.py)
    │
    ├─ 3. Enrich quality matches in parallel
    │       ├─ Hunter.io recruiter email lookup    (app/outreach/hunter.py)
    │       └─ Claude Haiku email drafter          (app/outreach/drafter.py)
    │
    ├─ 4. Persist ApplicationRecords + send outreach via SendGrid
    │
    └─ 5. Build XLSX report + email to REPORT_EMAIL  (app/report.py)
```

---

## API

### `POST /start`

Accepts `multipart/form-data`. All fields except `resume` have defaults.

| Field | Type | Default | Description |
|---|---|---|---|
| `resume` | file | required | PDF resume |
| `locations` | string | `"Bangalore"` | Comma-separated city names e.g. `"Bangalore,Mumbai"` |
| `country_code` | string | `"in"` | Adzuna country code (`in`, `gb`, `us`, etc.) |
| `remote` | bool | `false` | If true, searches without a location filter and appends "remote" to query |
| `years_of_experience` | float | null | Overrides the value parsed from the PDF |

**Response:**
```json
{"job_id": "abc123", "status": "queued"}
```

### `GET /health`

Returns `{"status": "ok"}`.

---

## Loop engineering

The core pipeline is a generator → evaluator → adversarial verifier chain. Each stage is an independent Claude call — no stage evaluates its own output.

```
Adzuna page → evaluate all 20 jobs concurrently → score ≥ 7 → verify (adversarial) → quality match
```

**Exit conditions** (whichever comes first):
- 20 confirmed quality matches (`MIN_QUALITY_MATCHES`)
- 100 total jobs evaluated (`MAX_EVALUATED`)
- Adzuna returns an empty page

**Evaluator** (`app/agents/evaluator.py`):
- Skeptical by default — low scores unless strong evidence of fit
- Dynamic seniority hard rule based on `years_of_experience`:
  - `yoe < 3` → Senior/Staff/Principal/Lead titles score ≤ 3
  - `yoe >= 6` → Junior/Intern/Trainee titles score ≤ 3
  - `3 ≤ yoe < 6` → no hard rule
- Prompt includes location and remote context from the profile

**Verifier** (`app/agents/verifier.py`):
- Tries to **refute** every evaluator score ≥ 7
- Defaults to `refuted=True` if uncertain or if Claude fails to return the tool
- Rejects on: hidden seniority, hard skill gap, wrong domain, explicit 5+ years requirement

**Crash safety**: state is committed to Postgres after each Adzuna page. Re-runs safely skip already-inserted jobs via `ON CONFLICT DO NOTHING` on `(adzuna_id, candidate_profile_id)`.

---

## Data flow through `profile` dict

The `profile` dict is the central object passed through the entire pipeline. It starts from `parse_resume()` and gets extra keys injected in `tasks.py` before the loop runs:

```python
# From resume parser:
profile = {
    "name": str,
    "target_role": str,
    "skills": list[str],
    "experience": list[dict],   # [{company, title, duration, summary}]
    "education": list[dict],    # [{institution, degree, year}]
    "years_of_experience": float,  # computed from experience durations
}

# Injected in tasks.py from request body:
profile["locations"] = ["Bangalore", "Mumbai"]  # parsed from comma-sep form field
profile["country_code"] = "in"
profile["remote"] = False
# years_of_experience overridden here if request body provided it
```

---

## Database models (`app/db.py`)

### `CandidateProfile`
One row per resume upload. Stores the parsed profile JSON + raw PDF text.

### `JobPosting`
One row per (job, candidate) pair. Unique constraint: `(adzuna_id, candidate_profile_id)` — same job can exist for different candidates but never duplicated per candidate.

### `ApplicationRecord`
Tracks outreach status per job match. Statuses: `pending → emailed / failed / skipped`.

**Cooling period**: before sending outreach, `tasks.py` queries `max(ApplicationRecord.created_at)` per `adzuna_id` where `status = "emailed"`. Jobs emailed within `OUTREACH_COOLING_DAYS` days are skipped. Jobs outside that window are re-sent. Prevents spam.

---

## External services

| Service | Used for | Key env var |
|---|---|---|
| Anthropic Claude Haiku | Resume parsing, job scoring, email drafting, adversarial verification | `ANTHROPIC_API_KEY` |
| Adzuna | Job discovery | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` |
| Hunter.io | Recruiter email lookup via company domain search | `HUNTER_API_KEY` |
| SendGrid | Outreach emails + XLSX report delivery | `SENDGRID_API_KEY` |

**Hunter.io**: uses domain search (not email finder). Prefers contacts with HR/recruiter/talent in department or position. Falls back to first available email.

**Adzuna**: country code goes in the URL path (`/v1/api/jobs/{country_code}/search/{page}`). `where` is a city name. For multiple locations, generator makes parallel calls and deduplicates by `adzuna_id`. For remote, `where` is omitted and "remote" is appended to the `what` query.

---

## Key configuration (`app/config.py`)

All config is loaded from environment at startup. Missing required keys raise `KeyError` immediately.

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | yes | — | |
| `ADZUNA_APP_ID` | yes | — | |
| `ADZUNA_APP_KEY` | yes | — | |
| `HUNTER_API_KEY` | yes | — | |
| `SENDGRID_API_KEY` | yes | — | |
| `DATABASE_URL` | yes | — | `postgresql+asyncpg://...` |
| `REDIS_URL` | yes | — | `redis://redis:6379` in Docker |
| `USER_EMAIL` | yes | — | Verified SendGrid sender address |
| `REPORT_EMAIL` | no | `USER_EMAIL` | Where XLSX report is sent (avoid self-send 403 by using a different address) |
| `OUTREACH_COOLING_DAYS` | no | `30` | Days before re-emailing the same job |

---

## Running locally (Docker)

```bash
cp .env.example .env
# fill in all keys

docker compose up           # first run: builds images, starts api + worker + postgres + redis
docker compose restart worker   # reload Python code changes (not just `up -d`)
```

**Important**: `docker compose up -d` does not reload Python modules if the container is already running. Always use `docker compose restart worker` after code changes.

Trigger a pipeline run:
```bash
curl -X POST http://localhost:8000/start \
  -F "resume=@Resume.pdf" \
  -F "locations=Bangalore,Mumbai" \
  -F "country_code=in" \
  -F "remote=false"
```

Watch worker logs:
```bash
docker compose logs worker -f
```

---

## Tests

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

Tests are in `tests/` and use mocks — no live API calls, no DB, no Redis required.

| File | What it covers |
|---|---|
| `tests/test_api.py` | `/start` form field parsing, defaults, non-PDF rejection |
| `tests/test_generator.py` | Single/multiple locations, remote flag, country code, deduplication |
| `tests/test_evaluator.py` | Seniority rules by yoe, location/remote in prompt |
| `tests/test_cooling.py` | Cooling window boundary conditions, custom days |

---

## File map

```
app/
  main.py                 FastAPI app — /start and /health endpoints
  config.py               Env var loading, fails fast on missing keys
  db.py                   SQLAlchemy models: CandidateProfile, JobPosting, ApplicationRecord
  agents/
    generator.py          Adzuna job discovery — handles multiple locations + remote
    evaluator.py          Claude Haiku scorer — dynamic seniority rules
    verifier.py           Adversarial Claude agent — tries to refute positive matches
    loop.py               Orchestrates generator → evaluator → verifier loop
  parsers/
    resume.py             pdfplumber + Claude Haiku — PDF → structured profile dict
  outreach/
    hunter.py             Hunter.io domain search — returns best recruiter email
    drafter.py            Claude Haiku — writes 3-4 sentence cold outreach email
    sendgrid_client.py    Sends email with optional XLSX attachment
  workers/
    tasks.py              ARQ task: full pipeline, cooling period check, report email
    arq_settings.py       ARQ WorkerSettings — registers run_pipeline function
  report.py               Builds styled XLSX from quality matches list
tests/
  test_api.py
  test_generator.py
  test_evaluator.py
  test_cooling.py
```
