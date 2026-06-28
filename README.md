# LoopHire

Automated job-hunting pipeline. Upload a resume PDF, get personalized cold-outreach emails sent to recruiters and an XLSX report in your inbox — fully automated.

## What it does

1. **Parses** your resume PDF into a structured candidate profile (Claude)
2. **Discovers** job postings from Adzuna across multiple locations and/or remote globally
3. **Scores** each job via a generator → evaluator → adversarial verifier loop (Claude)
4. **Finds** recruiter contact emails via Hunter.io domain search
5. **Drafts and sends** personalized cold-outreach emails via SendGrid
6. **Emails** an XLSX report with all matches, scores, and outreach status

## Stack

- **FastAPI** — `/start` endpoint accepts resume upload, serves frontend at `/`
- **ARQ + Redis** — background job queue
- **PostgreSQL + SQLAlchemy** — stores profiles, job scores, application records
- **Claude Haiku** — resume parsing, job scoring, adversarial verification, email drafting
- **Adzuna API** — job discovery (multiple countries, multi-city, remote)
- **Hunter.io** — recruiter email lookup via company domain search
- **SendGrid** — outreach + report delivery

## Loop engineering

Jobs are filtered through three independent Claude agents before outreach fires:

```
Adzuna → Generator → Evaluator (skeptic) → Adversarial Verifier → Outreach
```

- **Evaluator** scores 1–10; defaults low; seniority rule is dynamic based on `years_of_experience`
  - `yoe < 3` → Senior/Lead titles score ≤ 3
  - `yoe >= 6` → Junior/Intern titles score ≤ 3
- **Verifier** tries to refute every score ≥ 7; defaults to rejection if uncertain
- Loop exits at 20 confirmed matches or 100 evaluated — whichever comes first
- State committed to Postgres after each page (crash-safe)
- Outreach cooling period prevents re-emailing the same recruiter within N days

## Search logic

| Country | Cities | Remote | Behaviour |
|---|---|---|---|
| India | Bangalore | off | Bangalore onsite only |
| India | Bangalore, Mumbai | on | Both cities onsite + remote globally |
| India | *(none)* | off | All of India |
| India | *(none)* | on | All of India + remote globally |
| *(none)* | *(none)* | on | Remote globally only |

Remote global searches run against the `gb` Adzuna endpoint (largest remote dataset). At least one of country or remote must be provided.

## Setup

```bash
cp .env.example .env
# Fill in all keys in .env
docker compose up
```

Open `http://localhost:8000` for the web UI, or use the API directly.

After code changes:
```bash
docker compose restart worker
```

## API

```bash
# India, Bangalore onsite
curl -X POST http://localhost:8000/start \
  -F "resume=@Resume.pdf" \
  -F "country_code=in" \
  -F "locations=Bangalore"

# Multiple cities + remote
curl -X POST http://localhost:8000/start \
  -F "resume=@Resume.pdf" \
  -F "country_code=in" \
  -F "locations=Bangalore,Mumbai" \
  -F "remote=true"

# Remote only (global)
curl -X POST http://localhost:8000/start \
  -F "resume=@Resume.pdf" \
  -F "remote=true"
```

| Field | Required | Default | Description |
|---|---|---|---|
| `resume` | yes | — | PDF file |
| `country_code` | no* | — | Adzuna country code (`in`, `gb`, `us`, …) |
| `locations` | no | — | Comma-separated cities within the country |
| `remote` | no | `false` | Also search remote roles globally |
| `years_of_experience` | no | parsed from PDF | Override the resume-parsed value |

*At least one of `country_code` or `remote=true` is required.

Watch progress:
```bash
docker compose logs worker -f
```

## Tests

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

No live API calls — all external services are mocked.

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | yes | — | Anthropic API key |
| `ADZUNA_APP_ID` | yes | — | Adzuna app ID |
| `ADZUNA_APP_KEY` | yes | — | Adzuna app key |
| `HUNTER_API_KEY` | yes | — | Hunter.io API key |
| `SENDGRID_API_KEY` | yes | — | SendGrid API key |
| `DATABASE_URL` | yes | — | `postgresql+asyncpg://...` |
| `REDIS_URL` | yes | — | `redis://redis:6379` in Docker |
| `USER_EMAIL` | yes | — | Verified SendGrid sender address |
| `REPORT_EMAIL` | no | `USER_EMAIL` | Where the XLSX report is sent |
| `OUTREACH_COOLING_DAYS` | no | `30` | Days before re-emailing the same job |

## Project structure

```
app/
  main.py               FastAPI app — /start, /health, serves frontend
  config.py             Env var loading, fails fast on missing keys
  db.py                 SQLAlchemy models: CandidateProfile, JobPosting, ApplicationRecord
  agents/
    generator.py        Adzuna discovery — multi-location, remote, rate-limit safe
    evaluator.py        Claude scorer — dynamic seniority rules
    verifier.py         Adversarial Claude agent — tries to refute positive matches
    loop.py             Orchestrates generator → evaluator → verifier loop
  parsers/
    resume.py           pdfplumber + Claude — PDF → structured profile dict
  outreach/
    hunter.py           Hunter.io domain search — best recruiter email
    drafter.py          Claude — 3-4 sentence cold outreach email
    sendgrid_client.py  Sends email with optional XLSX attachment
  workers/
    tasks.py            ARQ task: full pipeline, cooling period, report email
    arq_settings.py     ARQ WorkerSettings
  report.py             Styled XLSX from quality matches
  static/
    index.html          Web UI — multi-city tag input, country/remote selector
tests/
  test_api.py
  test_generator.py
  test_evaluator.py
  test_cooling.py
```
