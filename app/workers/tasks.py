import asyncio
import logging
import os
import tempfile
from datetime import datetime, timedelta

from app.config import settings
from app.db import ApplicationRecord, Base, CandidateProfile, SessionLocal, engine
from app.agents.loop import run_loop
from app.outreach.drafter import draft_outreach_email
from app.outreach.hunter import find_recruiter_email
from app.outreach.sendgrid_client import send_email
from app.parsers.resume import parse_resume
from app.report import build_report

log = logging.getLogger(__name__)


async def _enrich_match(match: dict, profile: dict) -> dict:
    """Add recruiter_email and email_draft to a match dict in parallel."""
    recruiter_email, email_draft = await asyncio.gather(
        find_recruiter_email(match["company"]),
        draft_outreach_email(match, profile),
        return_exceptions=True,
    )
    match["recruiter_email"] = recruiter_email if not isinstance(recruiter_email, Exception) else None
    match["email_draft"] = email_draft if not isinstance(email_draft, Exception) else None
    if isinstance(recruiter_email, Exception):
        log.warning("Hunter failed for %s: %s", match["company"], recruiter_email)
    if isinstance(email_draft, Exception):
        log.warning("Drafter failed for %s: %s", match["title"], email_draft)
    return match


async def run_pipeline(
    ctx: dict,
    pdf_bytes: bytes,
    locations: list[str] | None = None,
    country_code: str = "in",
    remote: bool = False,
    years_of_experience_override: float | None = None,
) -> dict:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_bytes)
        pdf_path = f.name

    try:
        raw_text, profile_data = await parse_resume(pdf_path)
    finally:
        os.unlink(pdf_path)

    profile_data["locations"] = locations or ["Bangalore"]
    profile_data["country_code"] = country_code
    profile_data["remote"] = remote
    if years_of_experience_override is not None:
        profile_data["years_of_experience"] = years_of_experience_override

    async with SessionLocal() as session:
        profile = CandidateProfile(
            name=profile_data["name"],
            target_role=profile_data["target_role"],
            skills=profile_data["skills"],
            experience=profile_data["experience"],
            education=profile_data["education"],
            years_of_experience=profile_data.get("years_of_experience"),
            raw_text=raw_text,
        )
        session.add(profile)
        await session.commit()
        profile_id = profile.id

    async with SessionLocal() as session:
        matches = await run_loop(profile_data, profile_id, session)

    log.info("loop done: %d quality matches for profile %d", len(matches), profile_id)

    if not matches:
        log.warning("No quality matches found — skipping outreach and report")
        return {
            "profile_id": profile_id,
            "candidate_name": profile_data["name"],
            "quality_matches": 0,
        }

    # Enrich all matches in parallel: Hunter lookup + email draft
    enriched = await asyncio.gather(*[_enrich_match(m, profile_data) for m in matches])

    # Fetch DB ids for quality matches so we can FK into ApplicationRecord
    from sqlalchemy import select
    from app.db import ApplicationRecord as AR, JobPosting
    adzuna_ids = [m["adzuna_id"] for m in enriched]
    async with SessionLocal() as session:
        rows = await session.execute(
            select(JobPosting.id, JobPosting.adzuna_id)
            .where(JobPosting.adzuna_id.in_(adzuna_ids))
        )
        adzuna_to_db_id = {r.adzuna_id: r.id for r in rows}

        # Skip jobs emailed within the cooling window — allow re-send after it expires
        already_emailed = set()
        if adzuna_to_db_id:
            from sqlalchemy import func
            cooling_cutoff = datetime.utcnow() - timedelta(days=settings.outreach_cooling_days)
            sent_rows = await session.execute(
                select(JobPosting.adzuna_id, func.max(AR.created_at).label("last_sent"))
                .join(AR, AR.job_posting_id == JobPosting.id)
                .where(
                    JobPosting.adzuna_id.in_(adzuna_ids),
                    AR.status == "emailed",
                )
                .group_by(JobPosting.adzuna_id)
            )
            already_emailed = {r.adzuna_id for r in sent_rows if r.last_sent > cooling_cutoff}

    if already_emailed:
        log.info(
            "Skipping %d jobs emailed within the last %d days: %s",
            len(already_emailed), settings.outreach_cooling_days, already_emailed,
        )

    # Persist ApplicationRecords and send outreach emails
    async with SessionLocal() as session:
        for m in enriched:
            record = ApplicationRecord(
                job_posting_id=adzuna_to_db_id.get(m["adzuna_id"]),
                candidate_profile_id=profile_id,
                recruiter_email=m["recruiter_email"],
                email_draft=m["email_draft"],
                status="pending",
            )
            session.add(record)

            if m["adzuna_id"] in already_emailed:
                record.status = "skipped"
                log.info("Skipped (already emailed): %s at %s", m["title"], m["company"])
            elif m["recruiter_email"] and m["email_draft"]:
                try:
                    send_email(
                        to=m["recruiter_email"],
                        subject=f"Interested in {m['title']} at {m['company']}",
                        body=m["email_draft"],
                    )
                    record.status = "emailed"
                    log.info("Outreach sent to %s for %s", m["recruiter_email"], m["title"])
                except Exception as e:
                    record.status = "failed"
                    log.warning("SendGrid failed for %s: %s", m["company"], e)

        await session.commit()

    # Build and email the XLSX report
    xlsx = build_report(enriched)
    try:
        send_email(
            to=settings.report_email,
            subject=f"AutoApply Report — {profile_data['name']} ({len(enriched)} matches)",
            body=(
                f"Hi,\n\nYour AutoApply run completed.\n\n"
                f"Candidate: {profile_data['name']}\n"
                f"Quality matches found: {len(enriched)}\n"
                f"Outreach emails sent: {sum(1 for m in enriched if m.get('recruiter_email'))}\n\n"
                f"Full results attached.\n"
            ),
            xlsx_bytes=xlsx,
            xlsx_filename=f"autoapply_{profile_data['name'].replace(' ', '_')}.xlsx",
        )
        log.info("Report emailed to %s", settings.user_email)
    except Exception as e:
        log.error("Failed to send report email: %s", e)

    return {
        "profile_id": profile_id,
        "candidate_name": profile_data["name"],
        "quality_matches": len(enriched),
        "outreach_sent": sum(1 for m in enriched if m.get("status") == "emailed"),
    }
