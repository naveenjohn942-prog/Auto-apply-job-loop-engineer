# AutoApply

Personal job-hunting automation tool. Upload a resume PDF, get personalized outreach emails sent to recruiters and an XLSX report in your inbox — fully automated.

## What it does

1. **Parses** your resume PDF into a structured candidate profile (Claude)
2. **Discovers** job postings from Adzuna
3. **Scores** each job via a generator → evaluator → adversarial verifier loop (Claude)
4. **Finds** recruiter contact emails via Hunter.io domain search
5. **Drafts and sends** personalized cold-outreach emails via SendGrid
6. **Emails** an XLSX report with all matches, scores, and outreach status

## Stack

- **FastAPI** — `/start` endpoint accepts resume upload
- **ARQ + Redis** — background job queue
- **PostgreSQL + SQLAlchemy** — stores profiles, job scores, application records
- **Claude (Haiku)** — resume parsing, job scoring, email drafting
- **Adzuna API** — job discovery (India, Bangalore)
- **Hunter.io** — recruiter email lookup
- **SendGrid** — outreach + report delivery

## Loop engineering

Jobs are filtered through three independent Claude agents before outreach fires:

```
Adzuna → Generator → Evaluator (skeptic) → Adversarial Verifier → Outreach
```

- **Evaluator** scores 1–10; defaults low; hard rule: seniority titles score ≤ 3
- **Verifier** tries to refute every score ≥ 7; defaults to rejection if uncertain
- Loop exits at 20 confirmed matches or 100 evaluated — whichever comes first
- State committed to Postgres after each page (crash-safe)
- Already-emailed jobs are skipped on re-runs (no duplicate outreach)

## Setup

```bash
cp .env.example .env
# Fill in all keys in .env
docker compose up
```

## Run

```bash
# Minimal — defaults to Bangalore, India
curl -X POST http://localhost:8000/start -F "resume=@Resume.pdf"

# Multiple cities
curl -X POST http://localhost:8000/start \
  -F "resume=@Resume.pdf" \
  -F "locations=Bangalore,Mumbai" \
  -F "country_code=in"

# Remote jobs (UK)
curl -X POST http://localhost:8000/start \
  -F "resume=@Resume.pdf" \
  -F "country_code=gb" \
  -F "remote=true"
```

| Field | Default | Description |
|---|---|---|
| `resume` | required | PDF file |
| `locations` | `Bangalore` | Comma-separated cities |
| `country_code` | `in` | Adzuna country code (`in`, `gb`, `us`, …) |
| `remote` | `false` | Omits location filter, searches for remote roles |
| `years_of_experience` | parsed from PDF | Override the resume-parsed value |

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

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `ADZUNA_APP_ID` | Adzuna app ID |
| `ADZUNA_APP_KEY` | Adzuna app key |
| `HUNTER_API_KEY` | Hunter.io API key |
| `SENDGRID_API_KEY` | SendGrid API key |
| `DATABASE_URL` | Postgres connection string (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Redis connection string |
| `USER_EMAIL` | Verified SendGrid sender email (your email) |
| `REPORT_EMAIL` | Where the XLSX report is sent (defaults to `USER_EMAIL`) |
| `OUTREACH_COOLING_DAYS` | Days before re-emailing the same job (default: `30`) |

## Project structure

```
app/
  agents/
    generator.py   # Adzuna job discovery
    evaluator.py   # Claude scoring agent
    verifier.py    # Adversarial refutation agent
    loop.py        # Generator/evaluator/verifier orchestration
  outreach/
    hunter.py      # Recruiter email lookup
    drafter.py     # Claude email drafting
    sendgrid_client.py
  parsers/
    resume.py      # PDF → structured profile
  workers/
    tasks.py       # ARQ pipeline task
    arq_settings.py
  db.py            # SQLAlchemy models
  config.py
  main.py          # FastAPI app
  report.py        # XLSX generation
```
